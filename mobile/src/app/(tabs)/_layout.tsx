import * as React from "react";
import { ActivityIndicator, View } from "react-native";
import { Redirect, Tabs } from "expo-router";
import { Feather } from "@expo/vector-icons";
import { useAuth } from "@/lib/auth";

type FeatherName = React.ComponentProps<typeof Feather>["name"];
/** Real (Feather) tab icons — the lucide-equivalent the web uses; no emoji. The
 *  navigator passes the active/inactive tint as `color`. */
const tabIcon = (name: FeatherName) => {
  function TabIcon({ color, size }: { color: string; size: number }) {
    return <Feather name={name} size={size ?? 22} color={color} />;
  }
  return TabIcon;
};

export default function TabsLayout() {
  const { status } = useAuth();

  if (status === "loading") {
    return (
      <View className="flex-1 items-center justify-center bg-background">
        <ActivityIndicator color="#0d5c3a" />
      </View>
    );
  }
  if (status === "unauthenticated") return <Redirect href="/login" />;

  return (
    <Tabs
      screenOptions={{
        tabBarActiveTintColor: "#0d5c3a",
        tabBarInactiveTintColor: "#64748b",
        headerShown: true,
      }}
    >
      <Tabs.Screen name="index" options={{ title: "Dashboard", tabBarIcon: tabIcon("home") }} />
      <Tabs.Screen name="goals" options={{ title: "Goals", tabBarIcon: tabIcon("target") }} />
      <Tabs.Screen name="feedback" options={{ title: "Feedback", tabBarIcon: tabIcon("message-square") }} />
      <Tabs.Screen name="career" options={{ title: "Career", tabBarIcon: tabIcon("trending-up") }} />
      <Tabs.Screen name="more" options={{ title: "More", tabBarIcon: tabIcon("menu") }} />
    </Tabs>
  );
}
