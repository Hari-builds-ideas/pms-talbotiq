import { View, Text } from "react-native";

export default function Goals() {
  return (
    <View className="flex-1 items-center justify-center bg-background p-6">
      <Text className="text-lg font-semibold text-foreground">My goals & KPIs</Text>
      <Text className="mt-1 text-center text-sm text-muted-foreground">Record actuals and track your KPIs — arriving in BUILD_9.</Text>
    </View>
  );
}
