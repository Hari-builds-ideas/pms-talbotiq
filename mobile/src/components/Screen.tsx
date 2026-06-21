import * as React from "react";
import { View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

/** A screen container: background + top safe-area inset + horizontal padding. */
export function Screen({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  const insets = useSafeAreaInsets();
  return (
    <View className={`flex-1 bg-background ${className}`} style={{ paddingTop: insets.top }}>
      {children}
    </View>
  );
}
