export type PasswordValidationCode =
  | "PASSWORD_TOO_SHORT"
  | "PASSWORD_ASCII_NO_SPACE"
  | "PASSWORD_NEEDS_LETTER"
  | "PASSWORD_NEEDS_NUMBER"
  | "PASSWORD_NEEDS_SYMBOL";

export function normalizePassword(value: string): string {
  return value.normalize("NFKC");
}

export function validatePassword(value: string): PasswordValidationCode | null {
  const normalized = normalizePassword(value);
  if (normalized.length < 8) {
    return "PASSWORD_TOO_SHORT";
  }
  if (!/^[\x21-\x7E]+$/.test(normalized)) {
    return "PASSWORD_ASCII_NO_SPACE";
  }
  if (!/[A-Za-z]/.test(normalized)) {
    return "PASSWORD_NEEDS_LETTER";
  }
  if (!/\d/.test(normalized)) {
    return "PASSWORD_NEEDS_NUMBER";
  }
  if (!/[^A-Za-z0-9]/.test(normalized)) {
    return "PASSWORD_NEEDS_SYMBOL";
  }
  return null;
}
