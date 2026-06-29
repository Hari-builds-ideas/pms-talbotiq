import "../global.css";
import { Stack } from "expo-router";
import { QueryClientProvider } from "@tanstack/react-query";
import { SafeAreaProvider } from "react-native-safe-area-context";
import { GestureHandlerRootView } from "react-native-gesture-handler";
import { StatusBar } from "expo-status-bar";
import { queryClient } from "@/lib/query";
import { configureMobileApi } from "@/lib/api";
import { AuthProvider } from "@/lib/auth";

// Wire the shared API client (SecureStore tokens + the device-derived base URL)
// before any provider renders or fires a request.
configureMobileApi();

export default function RootLayout() {
  return (
    <GestureHandlerRootView style={{ flex: 1 }}>
      <SafeAreaProvider>
        <QueryClientProvider client={queryClient}>
          <AuthProvider>
            <StatusBar style="dark" />
            <Stack screenOptions={{ headerShown: false }}>
              <Stack.Screen name="index" />
              <Stack.Screen name="login" />
              <Stack.Screen name="(tabs)" />
              {/* Detail routes reached from the More tab (back + title via the header). */}
              <Stack.Screen name="checkins" options={{ headerShown: true, title: "Check-ins" }} />
              <Stack.Screen name="reviews" options={{ headerShown: true, title: "My reviews" }} />
              <Stack.Screen name="recognition" options={{ headerShown: true, title: "Recognition" }} />
              <Stack.Screen name="chat" options={{ headerShown: true, title: "AI assistant" }} />
            </Stack>
          </AuthProvider>
        </QueryClientProvider>
      </SafeAreaProvider>
    </GestureHandlerRootView>
  );
}
