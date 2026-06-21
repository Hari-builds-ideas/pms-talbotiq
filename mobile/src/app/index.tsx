import { Redirect } from "expo-router";
import { ActivityIndicator, View } from "react-native";
import { useAuth } from "@/lib/auth";

/** Entry: wait for the auth bootstrap, then route to the app or to login. */
export default function Index() {
  const { status } = useAuth();
  if (status === "loading") {
    return (
      <View className="flex-1 items-center justify-center bg-background">
        <ActivityIndicator color="#5B5BD6" />
      </View>
    );
  }
  return <Redirect href={status === "authenticated" ? "/(tabs)" : "/login"} />;
}
