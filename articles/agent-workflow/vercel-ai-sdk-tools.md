---
title: Vercel AI SDK — Building AI Apps with Tools
topics:
  - vercel-ai-sdk
  - typescript
  - nextjs
  - ai-development
  - tools
skills:
  - build-vercel-ai-agent
summary: >
  Advisory guide for the Vercel AI SDK — streamText, generateText, and tool definitions
  with Zod schemas, React hooks, multi-provider support, and structured output.
aliases:
  - vercel ai sdk
  - ai sdk nextjs
  - vercel ai tools
related:
  - spec-based-development
  - claude-agent-sdk-tools
  - anthropic-sdk-fastapi-tools
  - copilot-sdk-tools
last-updated:
---

# Vercel AI SDK — Building AI Apps with Tools

## Overview

The Vercel AI SDK (`npm install ai`) lets you build AI-powered applications with streaming, tool calling, and structured output. It handles the tool loop natively, supports 20+ model providers (swap by changing one string), and ships with React hooks for chat UIs — your job is to define tools and handle the UI.

> **Skill:** For step-by-step implementation including the minimal working example, use the `build-vercel-ai-agent` skill.

---

## The Three Things You Need

Every Vercel AI SDK project needs exactly three pieces:

| Object            | Lifecycle            | Description                                                             |
|-------------------|----------------------|-------------------------------------------------------------------------|
| `streamText()`    | One-shot, per request | Streams text + tool calls; returns `textStream`, `fullStream`, `usage` |
| `tool()`          | One per capability   | Built with `description`, `inputSchema` (Zod), and `execute` function  |
| `useChat()`       | One per UI component | React hook managing chat state, message history, and streaming          |

The SDK does the tool loop for you — when the model decides to call a tool, the SDK invokes your `execute` function and feeds the result back automatically.

---

## Authentication

Provider API keys via environment variables — never hard-code:

```bash
# Pick your provider(s)
ANTHROPIC_API_KEY="sk-ant-..."
OPENAI_API_KEY="sk-..."
GOOGLE_GENERATIVE_AI_API_KEY="..."
```

The SDK reads these automatically when using the corresponding provider package.

---

## Provider Configuration

Switch models by changing one string. No code changes needed:

```typescript
import { anthropic } from '@ai-sdk/anthropic';
import { openai } from '@ai-sdk/openai';

// Use Claude
streamText({ model: anthropic('claude-sonnet-4-6'), ... });

// Use GPT
streamText({ model: openai('gpt-4o'), ... });
```

Install the provider package you need:

```bash
npm install @ai-sdk/anthropic   # Claude
npm install @ai-sdk/openai      # GPT
npm install @ai-sdk/google      # Gemini
```

---

## Tool Definition

Define tools with Zod schemas for type-safe parameters:

```typescript
import { tool } from 'ai';
import { z } from 'zod';

const searchIssues = tool({
  description: 'Search Jira issues by query',
  inputSchema: z.object({
    query: z.string().describe('Search query string'),
    maxResults: z.number().default(10).describe('Max results to return'),
  }),
  execute: async ({ query, maxResults }) => {
    const results = await jira.search(query, maxResults);
    return results;
  },
});
```

Rules:
- Use `.describe()` on each field — the description is sent to the model
- The `execute` function can return any serializable value (not limited to strings)
- Each tool needs a unique name (the key in the `tools` object)

---

## Streaming vs. Blocking

| Function            | Returns                        | Use When                                    |
|---------------------|--------------------------------|---------------------------------------------|
| `streamText()`      | Async streams (`textStream`, `fullStream`) | Chat UIs, real-time display       |
| `generateText()`    | Complete result (awaited)      | Background processing, batch jobs           |

### Server-side streaming (Route Handler)

```typescript
import { streamText } from 'ai';
import { anthropic } from '@ai-sdk/anthropic';

export async function POST(req: Request) {
  const { messages } = await req.json();

  const result = streamText({
    model: anthropic('claude-sonnet-4-6'),
    messages,
    tools: { searchIssues },
    toolChoice: 'auto',
    onFinish: ({ usage }) => console.log('Tokens:', usage),
  });

  return result.toDataStreamResponse();
}
```

### Client-side with React hook

```typescript
import { useChat } from '@ai-sdk/react';

export function Chat() {
  const { messages, input, setInput, sendMessage, isLoading } = useChat();

  return (
    <div>
      {messages.map(m => <div key={m.id}>{m.content}</div>)}
      <input value={input} onChange={e => setInput(e.target.value)} />
      <button onClick={() => sendMessage()} disabled={isLoading}>Send</button>
    </div>
  );
}
```

---

## Tool Loop & Multi-Step

The SDK handles multi-step tool calling automatically:

1. Model generates a tool call
2. SDK executes your `execute` function
3. Result fed back to model
4. Model decides: respond to user or call another tool

Control with `toolChoice`:
- `'auto'` — model decides when to use tools (default)
- `'required'` — model must call at least one tool
- `'none'` — tools disabled for this request

---

## React Hooks

```typescript
import { useChat, useCompletion, useObject } from '@ai-sdk/react';
```

| Hook              | Purpose                                         |
|-------------------|-------------------------------------------------|
| `useChat()`       | Full chat interface with message history        |
| `useCompletion()` | Single text completion (no chat history)        |
| `useObject()`     | Stream structured JSON objects                  |

**AI SDK 5 breaking change:** `useChat()` no longer manages input state internally — you must handle `input`/`setInput` yourself.

---

## Structured Output

Generate typed objects directly:

```typescript
import { generateText, zodSchema } from 'ai';
import { z } from 'zod';

const { object } = await generateText({
  model: anthropic('claude-sonnet-4-6'),
  schema: zodSchema(z.object({
    title: z.string(),
    bugs: z.array(z.object({
      file: z.string(),
      line: z.number(),
      severity: z.enum(['low', 'medium', 'high']),
      description: z.string(),
    })),
  })),
  prompt: 'Analyze this code for bugs...',
});
```

For recursive/nested schemas, use `zodSchema(schema, { useReferences: true })`.

---

## Lifecycle Hooks

| Hook         | Available On    | Fires When              |
|--------------|-----------------|-------------------------|
| `onChunk`    | `streamText()`  | Each chunk arrives      |
| `onFinish`   | `streamText()`  | Stream completes        |
| `onError`    | `streamText()`  | Error occurs            |
| `onFinish`   | `useChat()`     | Response completes      |

```typescript
const result = streamText({
  model: anthropic('claude-sonnet-4-6'),
  messages,
  onFinish: ({ text, usage, finishReason }) => {
    console.log(`Done: ${usage.totalTokens} tokens, reason: ${finishReason}`);
  },
  onError: ({ error }) => {
    console.error('Stream error:', error);
  },
});
```

---

## Common Pitfalls

| Symptom                                    | Fix                                                                                        |
|--------------------------------------------|--------------------------------------------------------------------------------------------|
| Tool never called                          | Check `toolChoice` isn't `'none'`; ensure tool `description` is clear                     |
| Type errors on `inputSchema`               | AI SDK 5 renamed `parameters` → `inputSchema`; update accordingly                         |
| `useChat` input not working                | AI SDK 5 removed internal input state — manage `input`/`setInput` yourself                |
| Provider not found                         | Install the provider package: `npm install @ai-sdk/anthropic`                             |
| Recursive schema fails                     | Use `zodSchema(schema, { useReferences: true })`                                          |
| Zod `.describe()` not reaching model       | Call `.describe()` at the end of the schema chain, after all transforms                   |

---

## Related Articles

- **[spec-based-development](spec-based-development.md)** — Write architecture and feature specs before coding; complements SDK-based agent workflows.
- **[claude-agent-sdk-tools](claude-sdk-tools.md)** — Equivalent guide for Claude Agent SDK (Python).
- **[copilot-sdk-tools](copilot-sdk-tools.md)** — Equivalent guide for GitHub Copilot Python SDK.
- **[anthropic-sdk-fastapi-tools](anthropic-sdk-fastapi-tools.md)** — Build AI-powered APIs with Python FastAPI; pairs with this as a backend.
