import { ScrollView, Text, View } from "react-native";
import { useAuth } from "@/lib/auth";

/** Dashboard — placeholder shell for BUILD_8 8.2 (real cockpit data lands in 8.4).
 *  Shows the authenticated identity to prove login → me → routing works. */
export default function Dashboard() {
  const { me } = useAuth();
  const first = me?.display?.split(" ")[0] ?? "there";
  return (
    <ScrollView className="flex-1 bg-background" contentContainerClassName="p-5 gap-4">
      <View>
        <Text className="text-2xl font-bold text-foreground">Good to see you, {first}</Text>
        <Text className="mt-1 text-sm text-muted-foreground">
          {me?.role} · {me?.tenant_name ?? me?.tenant_slug}
        </Text>
      </View>
      <View className="rounded-xl border border-border bg-card p-4">
        <Text className="text-sm text-muted-foreground">
          Your cockpit — score, goals, nudges, feedback and roadmap — arrives in the next step (8.4).
          The app shell, secure login and navigation are live.
        </Text>
      </View>
    </ScrollView>
  );
}
