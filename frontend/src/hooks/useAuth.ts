import { useState } from "react";
import { api } from "../api/client";

export function useAuth() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function login(email: string, password: string): Promise<boolean> {
    setLoading(true);
    setError(null);
    try {
      // OAuth2PasswordRequestForm — field is named "username" but backend looks it up as email
      const form = new URLSearchParams({ username: email, password });
      const { data } = await api.post("/auth/token", form, {
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
      });
      localStorage.setItem("token", data.access_token);
      return true;
    } catch {
      setError("Invalid email or password");
      return false;
    } finally {
      setLoading(false);
    }
  }

  async function register(
    email: string,
    fullName: string,
    password: string,
    role: string
  ): Promise<boolean> {
    setLoading(true);
    setError(null);
    try {
      await api.post("/auth/register", {
        email,
        full_name: fullName,
        password,
        role,
      });
      return true;
    } catch (err: any) {
      setError(err.response?.data?.detail ?? "Registration failed");
      return false;
    } finally {
      setLoading(false);
    }
  }

  function logout() {
    localStorage.removeItem("token");
    window.location.href = "/login";
  }

  function currentRole(): string | null {
    const token = localStorage.getItem("token");
    if (!token) return null;
    try {
      const payload = JSON.parse(atob(token.split(".")[1]));
      return payload.role ?? null;
    } catch {
      return null;
    }
  }

  return { login, register, logout, currentRole, loading, error };
}
