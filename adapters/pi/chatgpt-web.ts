import { homedir } from "node:os";
import { join } from "node:path";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { StringEnum } from "@earendil-works/pi-ai";
import { Type } from "typebox";

const DEFAULT_MODEL = "GPT-5.6 Sol";
const DEFAULT_EFFORT = "high" as const;
const DEFAULT_TIMEOUT_SECONDS = 360;
const MIN_TIMEOUT_SECONDS = 30;
const MAX_TIMEOUT_SECONDS = 900;

type JsonObject = Record<string, unknown>;

type ChatGptAskParams = {
	question: string;
	search?: boolean;
	model?: string;
	effort?: "instant" | "medium" | "high";
	timeout?: number;
};

function isJsonObject(value: unknown): value is JsonObject {
	return typeof value === "object" && value !== null && !Array.isArray(value);
}

function parseJsonLine(value: string): JsonObject | undefined {
	try {
		const parsed: unknown = JSON.parse(value);
		return isJsonObject(parsed) ? parsed : undefined;
	} catch {
		return undefined;
	}
}

/** Find balanced JSON objects, while ignoring braces inside JSON strings. */
function parseLastJsonObject(stdout: string): JsonObject | undefined {
	const lines = stdout
		.split(/\r?\n/)
		.map((line) => line.trim())
		.filter(Boolean);
	for (let i = lines.length - 1; i >= 0; i--) {
		const parsed = parseJsonLine(lines[i]);
		if (parsed) return parsed;
	}

	const candidates: Array<{ start: number; end: number; value: JsonObject }> = [];
	for (let start = 0; start < stdout.length; start++) {
		if (stdout[start] !== "{") continue;

		let depth = 0;
		let inString = false;
		let escaped = false;
		for (let end = start; end < stdout.length; end++) {
			const char = stdout[end];
			if (inString) {
				if (escaped) escaped = false;
				else if (char === "\\") escaped = true;
				else if (char === '"') inString = false;
				continue;
			}
			if (char === '"') {
				inString = true;
			} else if (char === "{") {
				depth++;
			} else if (char === "}") {
				depth--;
				if (depth === 0) {
					const parsed = parseJsonLine(stdout.slice(start, end + 1));
					if (parsed) candidates.push({ start, end, value: parsed });
					break;
				}
			}
		}
	}

	const rootCandidates = candidates.filter(
		(candidate) =>
			!candidates.some(
				(other) =>
					other !== candidate &&
					other.start <= candidate.start &&
					other.end >= candidate.end &&
					(other.start < candidate.start || other.end > candidate.end),
			),
	);
	return rootCandidates[rootCandidates.length - 1]?.value;
}

function redactSensitive(text: string): string {
	return text
		.replace(/(^|\n)\s*cookie\s*[:=].*$/gim, "$1Cookie: [REDACTED]")
		.replace(
			/(\"?)(cookie|authorization|bearer|api[_-]?key|access[_-]?token|refresh[_-]?token|session(?:id)?|secret|password)\1\s*[:=]\s*(\"?)[^\s,;}\"]+\3/gi,
			"$1$2$1: $3[REDACTED]$3",
		)
		.replace(/\b(?:sk|sess|key|token|auth)[_-][A-Za-z0-9_-]{12,}\b/g, "[REDACTED]")
		.replace(/\b(?:ghp|github_pat|xoxb|xoxp)_[A-Za-z0-9_-]+\b/g, "[REDACTED]");
}

function stderrTail(stderr: string): string {
	const trimmed = redactSensitive(stderr.trim());
	return trimmed.length > 2000 ? trimmed.slice(-2000) : trimmed;
}

function getHermesCliPath(): string {
	const hermesHome = process.env.HERMES_HOME || join(homedir(), ".hermes");
	return join(hermesHome, "scripts", "chatgpt_web_cli.py");
}

function toolResult(text: string, details: JsonObject = {}) {
	return {
		content: [{ type: "text" as const, text }],
		details,
	};
}

const CHATGPT_ASK_PARAMETERS = Type.Object({
	question: Type.String({ description: "The question to ask through the logged-in ChatGPT web proxy." }),
	search: Type.Optional(Type.Boolean({ description: "Enable ChatGPT Web search for current information.", default: false })),
	model: Type.Optional(Type.String({ description: `ChatGPT model, default: ${DEFAULT_MODEL}.` })),
	effort: Type.Optional(
		StringEnum(["instant", "medium", "high"] as const, {
			description: "Reasoning effort; default high.",
		}),
	),
	timeout: Type.Optional(
		Type.Integer({
			description: `CLI timeout in seconds (${MIN_TIMEOUT_SECONDS}-${MAX_TIMEOUT_SECONDS}), default ${DEFAULT_TIMEOUT_SECONDS}.`,
			minimum: MIN_TIMEOUT_SECONDS,
			maximum: MAX_TIMEOUT_SECONDS,
			default: DEFAULT_TIMEOUT_SECONDS,
		}),
	),
});

export default function chatgptWebExtension(pi: ExtensionAPI) {
	pi.registerTool({
		name: "chatgpt_ask",
		label: "ChatGPT Web Ask",
		description:
			"Ask an already logged-in ChatGPT web proxy through Hermes. Set search=true for real-time information from the web. The default GPT-5.6 Sol with high effort is useful for complex reasoning, but this is not the first choice for a simple factual lookup.",
		promptSnippet: "Ask the logged-in ChatGPT web proxy; use search=true for current web information",
		promptGuidelines: [
			"Use chatgpt_ask for a second opinion or difficult reasoning via the logged-in ChatGPT web proxy.",
			"Set search=true when the answer depends on current web information; do not imply that an answer without search is real-time.",
			"Use the default high effort for difficult reasoning, but prefer direct Pi tools for simple, local, mechanical facts or edits.",
			"Do not put secrets, cookies, API keys, or private credentials in the question.",
		],
		parameters: CHATGPT_ASK_PARAMETERS,
		executionMode: "sequential",
		async execute(_toolCallId, params: ChatGptAskParams, signal) {
			const timeoutSeconds = Math.min(
				MAX_TIMEOUT_SECONDS,
				Math.max(MIN_TIMEOUT_SECONDS, Math.trunc(params.timeout ?? DEFAULT_TIMEOUT_SECONDS)),
			);
			const model = params.model?.trim() || DEFAULT_MODEL;
			const effort = params.effort || DEFAULT_EFFORT;
			const args = ["ask", params.question, "--model", model, "--effort", effort, "--timeout", String(timeoutSeconds)];
			if (params.search === true) args.push("--search");

			try {
				const result = await pi.exec("python3", [getHermesCliPath(), ...args], {
					signal,
					timeout: timeoutSeconds * 1000,
				});
				const payload = parseLastJsonObject(result.stdout);
				if (result.code !== 0 || result.killed) {
					const reason = result.killed ? "the process was terminated (possibly by timeout or cancellation)" : `exit code ${result.code}`;
					// The CLI prints {"success": false, "error": ...} to stdout on
					// failure; surface it instead of reporting a bare exit code.
					const cliError = payload && typeof payload.error === "string"
						? ` CLI error: ${redactSensitive(payload.error)}`
						: "";
					const partial = payload && typeof payload.partial === "string" && payload.partial.trim()
						? ` Partial answer: ${redactSensitive(payload.partial.slice(0, 300))}`
						: "";
					const error = `chatgpt_ask failed: ${reason}.${cliError}${partial}${result.stderr.trim() ? ` Stderr tail: ${stderrTail(result.stderr)}` : ""}`;
					return toolResult(error, { success: false, code: result.code, killed: result.killed, ...(payload ?? {}) });
				}
				if (!payload) {
					return toolResult(
						`chatgpt_ask failed: the CLI did not return a JSON object.${result.stderr.trim() ? ` Stderr tail: ${stderrTail(result.stderr)}` : ""}`,
						{ success: false, code: result.code },
					);
				}
				if (payload.success === false) {
					const message = typeof payload.error === "string" ? payload.error : "the ChatGPT web request was unsuccessful";
					const failureDetails: JsonObject = {
						success: false,
						model: payload.model ?? model,
						effort: payload.effort ?? effort,
						search: payload.search ?? params.search === true,
						url: payload.url,
						elapsed_s: payload.elapsed_s,
					};
					return toolResult(
						`chatgpt_ask failed: ${redactSensitive(message)}${result.stderr.trim() ? ` Stderr tail: ${stderrTail(result.stderr)}` : ""}`,
						failureDetails,
					);
				}

				const response: JsonObject = {
					success: payload.success ?? true,
					answer: payload.answer,
					model: payload.model ?? model,
					effort: payload.effort ?? effort,
					search: payload.search ?? params.search === true,
					url: payload.url,
					elapsed_s: payload.elapsed_s,
				};
				return toolResult(JSON.stringify(response), response);
			} catch (error) {
				const message = error instanceof Error ? error.message : String(error);
				return toolResult(`chatgpt_ask failed: ${redactSensitive(message)}`, { success: false });
			}
		},
	});
}
