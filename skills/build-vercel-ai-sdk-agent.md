---
title: Build a Vercel AI SDK Agent
type: skill
summary: >
  Step-by-step skill for building a Next.js AI app with the Vercel AI SDK.
  Covers setup, tool definition with Zod, streaming routes, React hooks, and structured output.
references:
  - articles/agent-workflow/vercel-ai-sdk-tools.md
last-updated:
---

# Build a Vercel AI SDK Agent

Executable steps for building an AI-powered app using the Vercel AI SDK and Next.js. Follow in order.

---

## Phase 1: Project Setup

### Step 1.1: Create project structure

```
project/
├── app/
│   ├── api/
│   │   └── chat/
│   │       └── route.ts      # API route handler
│   ├── page.tsx              # Chat UI
│   └── layout.tsx
├── lib/
│   └── tools.ts              # Tool definitions
├── package.json
└── .env.local                # API keys (never commit)
```

### Step 1.2: Install dependencies

```bash
npx create-next-app@latest my-ai-app --typescript --tailwind --app
cd my-ai-app
npm install ai @ai-sdk/anthropic zod
```

### Step 1.3: Set authentication

```bash
# .env.local
ANTHROPIC_API_KEY="sk-ant-..."
```

For other providers:

```bash
OPENAI_API_KEY="sk-..."
GOOGLE_GENERATIVE_AI_API_KEY="..."
```

---

## Phase 2: Define Tools

### Step 2.1: Create tool with Zod schema

```typescript
// lib/tools.ts
import { tool } from 'ai';
import { z } from 'zod';

export const searchIssues = tool({
  description: 'Search Jira issues by query',
  inputSchema: z.object({
    query: z.string().describe('Search query string'),
    maxResults: z.number().default(10).describe('Max results to return'),
  }),
  execute: async ({ query, maxResults }) => {
    const results = await fetch(`/api/jira?q=${query}&limit=${maxResults}`);
    return results.json();
  },
});
```

Rules:
- Use `.describe()` on every Zod field — sent to the model as documentation
- `execute` can return any serializable value (not limited to strings)
- Each tool key in the `tools` object must be unique and descriptive
- Call `.describe()` at the end of schema chains, after transforms

### Step 2.2: Group tools for export

```typescript
// lib/tools.ts
export const tools = {
  searchIssues,
  getWeather,
  createTicket,
};
```

---

## Phase 3: Create API Route

### Step 3.1: Streaming route handler

```typescript
// app/api/chat/route.ts
import { streamText } from 'ai';
import { anthropic } from '@ai-sdk/anthropic';
import { tools } from '@/lib/tools';

export async function POST(req: Request) {
  const { messages } = await req.json();

  const result = streamText({
    model: anthropic('claude-sonnet-4-6'),
    messages,
    tools,
    toolChoice: 'auto',
    onFinish: ({ usage }) => {
      console.log(`Tokens: ${usage.totalTokens}`);
    },
  });

  return result.toDataStreamResponse();
}
```

### Step 3.2: Non-streaming route (for background jobs)

```typescript
import { generateText } from 'ai';
import { anthropic } from '@ai-sdk/anthropic';
import { tools } from '@/lib/tools';

export async function POST(req: Request) {
  const { prompt } = await req.json();

  const { text, toolCalls, usage } = await generateText({
    model: anthropic('claude-sonnet-4-6'),
    prompt,
    tools,
  });

  return Response.json({ text, toolCalls, usage });
}
```

---

## Phase 4: Build the Chat UI

### Step 4.1: Basic chat component with useChat

```typescript
// app/page.tsx
'use client';

import { useChat } from '@ai-sdk/react';
import { useState } from 'react';

export default function Chat() {
  const { messages, sendMessage, isLoading } = useChat();
  const [input, setInput] = useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim()) return;
    sendMessage(input);
    setInput('');
  };

  return (
    <div className="flex flex-col h-screen max-w-2xl mx-auto p-4">
      <div className="flex-1 overflow-y-auto space-y-4">
        {messages.map((m) => (
          <div key={m.id} className={m.role === 'user' ? 'text-right' : 'text-left'}>
            <span className="inline-block p-3 rounded-lg bg-gray-100">
              {m.content}
            </span>
          </div>
        ))}
      </div>

      <form onSubmit={handleSubmit} className="flex gap-2 pt-4">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Type a message..."
          className="flex-1 p-2 border rounded"
          disabled={isLoading}
        />
        <button type="submit" disabled={isLoading} className="px-4 py-2 bg-blue-500 text-white rounded">
          Send
        </button>
      </form>
    </div>
  );
}
```

---

## Phase 5: Structured Output (Optional)

### Step 5.1: Generate typed objects

```typescript
import { generateText, zodSchema } from 'ai';
import { anthropic } from '@ai-sdk/anthropic';
import { z } from 'zod';

const BugReport = z.object({
  title: z.string(),
  bugs: z.array(z.object({
    file: z.string(),
    line: z.number(),
    severity: z.enum(['low', 'medium', 'high']),
    description: z.string(),
  })),
});

export async function analyzeBugs(code: string) {
  const { object } = await generateText({
    model: anthropic('claude-sonnet-4-6'),
    schema: zodSchema(BugReport),
    prompt: `Analyze this code for bugs:\n\n${code}`,
  });

  return object; // Fully typed as z.infer<typeof BugReport>
}
```

### Step 5.2: Stream objects to the client

```typescript
// app/api/analyze/route.ts
import { streamObject } from 'ai';
import { anthropic } from '@ai-sdk/anthropic';

export async function POST(req: Request) {
  const { code } = await req.json();

  const result = streamObject({
    model: anthropic('claude-sonnet-4-6'),
    schema: zodSchema(BugReport),
    prompt: `Analyze this code for bugs:\n\n${code}`,
  });

  return result.toTextStreamResponse();
}
```

Client-side with `useObject`:

```typescript
import { useObject } from '@ai-sdk/react';

const { object, isLoading } = useObject({
  api: '/api/analyze',
  schema: BugReport,
});
```

---

## Phase 6: Multi-Provider Support (Optional)

### Step 6.1: Swap providers without code changes

```typescript
import { anthropic } from '@ai-sdk/anthropic';
import { openai } from '@ai-sdk/openai';
import { google } from '@ai-sdk/google';

const models = {
  fast: anthropic('claude-haiku-4-5'),
  balanced: anthropic('claude-sonnet-4-6'),
  powerful: anthropic('claude-opus-4-6'),
  gpt: openai('gpt-4o'),
  gemini: google('gemini-2.0-flash'),
};

streamText({
  model: models[selectedModel],
  messages,
  tools,
});
```

Install only what you need:

```bash
npm install @ai-sdk/anthropic   # Claude
npm install @ai-sdk/openai      # GPT
npm install @ai-sdk/google      # Gemini
```

---

## Phase 7: Lifecycle Hooks (Optional)

### Step 7.1: Add callbacks to streamText

```typescript
const result = streamText({
  model: anthropic('claude-sonnet-4-6'),
  messages,
  tools,
  onChunk: ({ chunk }) => {
    // Fires on each chunk — logging, metrics
  },
  onFinish: ({ text, usage, finishReason }) => {
    // Save to DB, log usage, trigger follow-up
    await saveConversation(messages, text);
    console.log(`${usage.totalTokens} tokens, reason: ${finishReason}`);
  },
  onError: ({ error }) => {
    console.error('Stream error:', error);
  },
});
```

---

## Minimal Working Example

Complete copy-paste Next.js app:

**`app/api/chat/route.ts`**

```typescript
import { streamText, tool } from 'ai';
import { anthropic } from '@ai-sdk/anthropic';
import { z } from 'zod';

const greetUser = tool({
  description: 'Greet a user by name',
  inputSchema: z.object({
    name: z.string().describe('Name to greet'),
  }),
  execute: async ({ name }) => `Hello, ${name}! Welcome aboard.`,
});

export async function POST(req: Request) {
  const { messages } = await req.json();

  const result = streamText({
    model: anthropic('claude-sonnet-4-6'),
    messages,
    tools: { greetUser },
    toolChoice: 'auto',
  });

  return result.toDataStreamResponse();
}
```

**`app/page.tsx`**

```typescript
'use client';
import { useChat } from '@ai-sdk/react';
import { useState } from 'react';

export default function Chat() {
  const { messages, sendMessage, isLoading } = useChat();
  const [input, setInput] = useState('');

  return (
    <main className="max-w-xl mx-auto p-4">
      {messages.map((m) => (
        <p key={m.id}><b>{m.role}:</b> {m.content}</p>
      ))}
      <form onSubmit={(e) => { e.preventDefault(); sendMessage(input); setInput(''); }}>
        <input value={input} onChange={(e) => setInput(e.target.value)} disabled={isLoading} />
        <button type="submit">Send</button>
      </form>
    </main>
  );
}
```

---

## Checklist

- [ ] `ANTHROPIC_API_KEY` (or other provider key) set in `.env.local`
- [ ] `npm install ai @ai-sdk/anthropic zod` completed
- [ ] Each tool has a unique key and clear `description`
- [ ] Zod `.describe()` used on all input fields
- [ ] `toolChoice` set appropriately (`'auto'` / `'required'` / `'none'`)
- [ ] API route returns `result.toDataStreamResponse()`
- [ ] Client uses `useChat()` with manual input state (AI SDK 5)
- [ ] `inputSchema` used (not deprecated `parameters`)
