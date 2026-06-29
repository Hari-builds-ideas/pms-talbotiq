import * as React from "react";
import { KeyboardAvoidingView, Platform, Pressable, ScrollView, Text, TextInput, View } from "react-native";
import { useMutation } from "@tanstack/react-query";
import { aiApi } from "@shared/api/endpoints";
import { mapApiError } from "@shared/errors";
import type { ChatResponse } from "@shared/types";
import { Badge } from "@/components/ui";

interface Turn {
  role: "user" | "assistant";
  text: string;
  blocked?: boolean;
  data?: string[];
}

/** AI assistant — READ-ONLY on mobile: ask about your goals, KPIs, reviews or team
 *  (RBAC-scoped server-side; it only answers from what you can already see). Write
 *  actions (approve / start / enrich) stay on the web confirm-card flow — here a
 *  write request just returns the assistant's read-only reply. */
export default function Chat() {
  const [turns, setTurns] = React.useState<Turn[]>([]);
  const [input, setInput] = React.useState("");
  const scrollRef = React.useRef<ScrollView>(null);

  const ask = useMutation({
    mutationFn: (q: string) => aiApi.chat(q),
    onSuccess: (res: ChatResponse) => {
      const data = Array.isArray(res.data) ? (res.data as string[]) : undefined;
      setTurns((t) => [...t, { role: "assistant", text: res.answer, blocked: res.status !== "ok", data }]);
    },
    onError: (err) => {
      setTurns((t) => [...t, { role: "assistant", text: mapApiError(err).message, blocked: true }]);
    },
  });

  React.useEffect(() => {
    scrollRef.current?.scrollToEnd({ animated: true });
  }, [turns, ask.isPending]);

  function send() {
    const q = input.trim();
    if (!q) return;
    setTurns((t) => [...t, { role: "user", text: q }]);
    setInput("");
    ask.mutate(q);
  }

  return (
    <KeyboardAvoidingView
      behavior={Platform.OS === "ios" ? "padding" : undefined}
      className="flex-1 bg-background"
      keyboardVerticalOffset={90}
    >
      <ScrollView ref={scrollRef} className="flex-1" contentContainerClassName="p-4 gap-3" keyboardShouldPersistTaps="handled">
        {turns.length === 0 ? (
          <View className="items-center gap-2 pt-8">
            <Text className="text-center text-sm text-muted-foreground">
              Ask about your goals, KPIs, reviews or team — within what you can see.
            </Text>
            {["How many open reviews do I have?", "What are my goals?"].map((s) => (
              <Pressable key={s} onPress={() => setInput(s)} className="rounded-full border border-border bg-card px-3 py-1.5">
                <Text className="text-xs text-muted-foreground">{s}</Text>
              </Pressable>
            ))}
          </View>
        ) : (
          turns.map((t, i) => <Bubble key={i} turn={t} />)
        )}
        {ask.isPending ? <Text className="text-sm text-muted-foreground">…</Text> : null}
      </ScrollView>

      <View className="flex-row items-center gap-2 border-t border-border bg-card p-3">
        <TextInput
          value={input}
          onChangeText={setInput}
          placeholder="Ask a question…"
          className="flex-1 rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground"
          onSubmitEditing={send}
          returnKeyType="send"
        />
        <Pressable
          onPress={send}
          disabled={!input.trim() || ask.isPending}
          className={`rounded-lg bg-primary px-4 py-2.5 ${!input.trim() || ask.isPending ? "opacity-50" : ""}`}
        >
          <Text className="text-sm font-semibold text-primary-foreground">Send</Text>
        </Pressable>
      </View>
    </KeyboardAvoidingView>
  );
}

function Bubble({ turn }: { turn: Turn }) {
  const isUser = turn.role === "user";
  return (
    <View className={`max-w-[85%] ${isUser ? "self-end" : "self-start"}`}>
      <View className={`rounded-2xl px-3.5 py-2.5 ${isUser ? "bg-primary" : "bg-card border border-border"}`}>
        {turn.blocked ? (
          <View className="mb-1 self-start">
            <Badge tone="warning">Read-only</Badge>
          </View>
        ) : null}
        <Text className={`text-sm ${isUser ? "text-primary-foreground" : "text-foreground"}`}>{turn.text}</Text>
        {turn.data && turn.data.length > 0 ? (
          <View className="mt-1.5 gap-0.5">
            {turn.data.map((d, i) => (
              <Text key={i} className={`text-xs ${isUser ? "text-primary-foreground/90" : "text-muted-foreground"}`}>
                • {d}
              </Text>
            ))}
          </View>
        ) : null}
      </View>
    </View>
  );
}
