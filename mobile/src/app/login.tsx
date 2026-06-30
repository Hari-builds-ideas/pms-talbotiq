import * as React from "react";
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  Text,
  TextInput,
  View,
} from "react-native";
import { Redirect } from "expo-router";
import { useForm, Controller } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { authApi } from "@shared/api/endpoints";
import { mapApiError } from "@shared/errors";
import type { LoginResponse } from "@shared/types";
import { useAuth } from "@/lib/auth";
import { apiBaseUrl } from "@/lib/api";
import { Screen } from "@/components/Screen";

const schema = z.object({
  tenant_slug: z.string().min(1, "Workspace is required"),
  email: z.string().min(1, "Email is required").email("Enter a valid email"),
  password: z.string().min(1, "Password is required"),
});
type Form = z.infer<typeof schema>;

export default function Login() {
  const { status, completeLogin } = useAuth();
  const [error, setError] = React.useState<string | null>(null);
  const [mfa, setMfa] = React.useState<{ challenge?: string } | null>(null);
  const [code, setCode] = React.useState("");
  const [busy, setBusy] = React.useState(false);

  const { control, handleSubmit, formState } = useForm<Form>({
    resolver: zodResolver(schema),
    defaultValues: { tenant_slug: "acme", email: "", password: "" },
  });

  if (status === "authenticated") return <Redirect href="/(tabs)" />;

  async function onSubmit(values: Form) {
    setError(null);
    setBusy(true);
    try {
      const res: LoginResponse = await authApi.login(values);
      if (res.mfa_required) {
        setMfa({ challenge: res.challenge });
      } else if (res.access && res.refresh) {
        await completeLogin({ access: res.access, refresh: res.refresh });
      } else {
        setError("Unexpected login response. Please try again.");
      }
    } catch (e) {
      setError(mapApiError(e).message);
    } finally {
      setBusy(false);
    }
  }

  async function submitMfa() {
    setError(null);
    setBusy(true);
    try {
      const tokens = await authApi.mfaChallenge({ challenge: mfa?.challenge, code: code.trim() });
      await completeLogin(tokens);
    } catch (e) {
      setError(mapApiError(e).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Screen>
      <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} className="flex-1">
        <ScrollView contentContainerClassName="flex-grow justify-center px-6 py-10" keyboardShouldPersistTaps="handled">
          <Text className="text-3xl font-bold text-foreground">Talbotiq PMS</Text>
          <Text className="mt-1 text-base text-muted-foreground">Sign in to your workspace</Text>

          {error ? (
            <View className="mt-4 rounded-lg bg-danger-subtle px-3 py-2">
              <Text className="text-sm text-danger">{error}</Text>
            </View>
          ) : null}

          {!mfa ? (
            <View className="mt-6 gap-4">
              <Field name="tenant_slug" label="Workspace" control={control} placeholder="acme" autoCapitalize="none" />
              <Field name="email" label="Email" control={control} placeholder="you@company.com" autoCapitalize="none" keyboardType="email-address" />
              <Field name="password" label="Password" control={control} placeholder="••••••••" secureTextEntry />
              <PrimaryButton label="Sign in" busy={busy || formState.isSubmitting} onPress={handleSubmit(onSubmit)} />
            </View>
          ) : (
            <View className="mt-6 gap-4">
              <Text className="text-sm text-muted-foreground">
                Enter the 6-digit code from your authenticator app.
              </Text>
              <View className="gap-1.5">
                <Text className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Code</Text>
                <TextInput
                  value={code}
                  onChangeText={setCode}
                  placeholder="123456"
                  keyboardType="number-pad"
                  className="rounded-lg border border-border bg-card px-3 py-3 text-base text-foreground"
                />
              </View>
              <PrimaryButton label="Verify" busy={busy} onPress={submitMfa} />
              <Pressable onPress={() => { setMfa(null); setCode(""); }}>
                <Text className="text-center text-sm text-primary">Back</Text>
              </Pressable>
            </View>
          )}

          <Text className="mt-8 text-center text-2xs text-muted-foreground">{apiBaseUrl}</Text>
        </ScrollView>
      </KeyboardAvoidingView>
    </Screen>
  );
}

function Field({
  name, label, control, ...input
}: { name: keyof Form; label: string; control: ReturnType<typeof useForm<Form>>["control"] } & React.ComponentProps<typeof TextInput>) {
  return (
    <Controller
      control={control}
      name={name}
      render={({ field: { onChange, onBlur, value }, fieldState }) => (
        <View className="gap-1.5">
          <Text className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{label}</Text>
          <TextInput
            value={value}
            onChangeText={onChange}
            onBlur={onBlur}
            className="rounded-lg border border-border bg-card px-3 py-3 text-base text-foreground"
            placeholderTextColor="#94a3b8"
            {...input}
          />
          {fieldState.error ? <Text className="text-xs text-danger">{fieldState.error.message}</Text> : null}
        </View>
      )}
    />
  );
}

function PrimaryButton({ label, busy, onPress }: { label: string; busy?: boolean; onPress: () => void }) {
  return (
    <Pressable
      onPress={onPress}
      disabled={busy}
      className={`mt-2 items-center rounded-lg py-3.5 ${busy ? "bg-primary/60" : "bg-primary"}`}
    >
      {busy ? <ActivityIndicator color="#fff" /> : <Text className="text-base font-semibold text-primary-foreground">{label}</Text>}
    </Pressable>
  );
}
