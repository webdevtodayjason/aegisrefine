import { NextResponse, type NextRequest } from "next/server";

// UX gate only — real auth is enforced by the API. If a request for an authed page
// arrives without the session cookie, bounce to /login (the API would 401 anyway).
const SESSION_COOKIE = "aegis_session";

export function middleware(req: NextRequest) {
  if (!req.cookies.has(SESSION_COOKIE)) {
    const login = new URL("/login", req.url);
    return NextResponse.redirect(login);
  }
  return NextResponse.next();
}

// Guard the authed surfaces; everything else (landing, /login, assets) is public.
export const config = {
  matcher: [
    "/dashboard",
    "/new-order",
    "/orders",
    "/orders/:path*",
    "/certificate",
    "/billing",
    "/settings",
  ],
};
