import { View, Text } from "react-native";

export default function Feedback() {
  return (
    <View className="flex-1 items-center justify-center bg-background p-6">
      <Text className="text-lg font-semibold text-foreground">360 feedback</Text>
      <Text className="mt-1 text-center text-sm text-muted-foreground">Give feedback and view your released summary — arriving in BUILD_9.</Text>
    </View>
  );
}
