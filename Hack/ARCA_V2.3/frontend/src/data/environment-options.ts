import type { EnvironmentId } from "@/types/dashboard";

export const environmentOptions: { value: EnvironmentId; label: string }[] = [
  { value: "all", label: "All environments" },
  { value: "azure", label: "Azure" },
  { value: "aws", label: "AWS" },
  { value: "snowflake", label: "Snowflake" },
];
