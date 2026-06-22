/** @type {import('next').NextConfig} */
const nextConfig = {
  // Self-contained build output so the Docker runtime image stays small and
  // does not need node_modules copied in.
  output: "standalone",
  // `pg` is a native-ish server dependency used only by Better Auth on the
  // server; keep it external to the server bundle.
  serverExternalPackages: ["pg"],
};

export default nextConfig;
