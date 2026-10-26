/** Same-origin proxy: the HttpOnly session cookie needs no CORS and tokens never reach page JS. */
module.exports = {
  output: "standalone",
  async rewrites() {
    const api = process.env.API_URL || "http://localhost:8000";
    return [{ source: "/api/v1/:path*", destination: `${api}/api/v1/:path*` }];
  },
};
