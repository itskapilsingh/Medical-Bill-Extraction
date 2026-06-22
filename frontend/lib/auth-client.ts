"use client";

import { createAuthClient } from "better-auth/react";

// No baseURL → the client talks to the same origin it is served from
// (http://localhost:3000), where the Better Auth route handler lives.
export const authClient = createAuthClient();

export const { signIn, signUp, signOut, useSession } = authClient;
