import { z } from "zod";

import { ALLERGENS, DIETS, EQUIPMENT, EXERCISES, EXPERIENCE, GOALS, HEALTH_FLAGS } from "../api/types";

export const credentialsSchema = z.object({
  email: z.email("Enter a valid email address"),
  password: z.string().min(1, "Enter your password").max(72),
});

export const registerSchema = z
  .object({
    email: z.email("Enter a valid email address"),
    password: z
      .string()
      .min(8, "At least 8 characters")
      .max(72, "At most 72 characters")
      .regex(/[A-Za-z]/, "Include at least one letter")
      .regex(/\d/, "Include at least one digit"),
    confirm: z.string(),
  })
  .refine((v) => v.password === v.confirm, { path: ["confirm"], message: "Passwords do not match" });

const optionalNumber = (min: number, max: number, name: string) =>
  z.number().min(min, `${name} must be at least ${min}`).max(max, `${name} must be at most ${max}`).nullable();

export const profileSchema = z.object({
  display_name: z.string().trim().max(80).nullable(),
  age: optionalNumber(13, 100, "Age").refine((v) => v === null || Number.isInteger(v), "Age must be a whole number"),
  sex: z.enum(["female", "male", "unspecified"]),
  height_cm: optionalNumber(100, 250, "Height"),
  weight_kg: optionalNumber(30, 300, "Weight"),
  goal: z.enum(GOALS),
  experience: z.enum(EXPERIENCE),
  equipment: z.array(z.enum(EQUIPMENT)),
  days_per_week: z.number().int().min(1).max(6),
  preferred_days: z.array(z.number().int().min(0).max(6)),
  session_minutes: z.number().int().min(10, "At least 10 minutes").max(120, "At most 120 minutes"),
  exclusions: z.array(z.enum(EXERCISES)).max(4, "Keep at least one exercise"),
  dietary_preferences: z.array(z.enum(DIETS)),
  allergies: z.array(z.enum(ALLERGENS)),
  health_flags: z.array(z.enum(HEALTH_FLAGS)),
});

export type FieldErrors = Record<string, string>;

export function fieldErrors(error: z.ZodError): FieldErrors {
  const out: FieldErrors = {};
  for (const issue of error.issues) {
    const key = issue.path.join(".") || "form";
    out[key] ??= issue.message;
  }
  return out;
}
