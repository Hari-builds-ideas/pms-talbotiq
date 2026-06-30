import * as React from "react";
import { ActivityIndicator, Text, View } from "react-native";
import { Redirect, Tabs } from "expo-router";
import { useAuth } from "@/lib/auth";

const tabIcon = (emoji: string) => {
  function TabIcon({ focused }: { focused: boolean }) {
    return <Text style={{ fontSize: 20, opacity: focused ? 1 : 0.45 }}>{emoji}</Text>;
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
      <Tabs.Screen name="index" options={{ title: "Dashboard", tabBarIcon: tabIcon("🏠") }} />
      <Tabs.Screen name="goals" options={{ title: "Goals", tabBarIcon: tabIcon("🎯") }} />
      <Tabs.Screen name="feedback" options={{ title: "Feedback", tabBarIcon: tabIcon("💬") }} />
      <Tabs.Screen name="career" options={{ title: "Career", tabBarIcon: tabIcon("🚀") }} />
      <Tabs.Screen name="more" options={{ title: "More", tabBarIcon: tabIcon("☰") }} />
    </Tabs>
  );
}
