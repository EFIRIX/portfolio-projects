var config = {
    content: ["./index.html", "./src/**/*.{ts,tsx}"],
    theme: {
        extend: {
            fontFamily: {
                display: ["Space Grotesk", "sans-serif"],
                body: ["Sora", "sans-serif"],
            },
            colors: {
                aurora: {
                    night: "#0B0F1A",
                    deep: "#12172A",
                    glowA: "#4F7BFF",
                    glowB: "#8F6BFF",
                    cyan: "#00E5FF",
                    slate: "#98A8C3",
                },
            },
            boxShadow: {
                glow: "0 0 40px rgba(79, 123, 255, 0.25)",
                panel: "0 20px 60px rgba(0, 0, 0, 0.45)",
            },
            keyframes: {
                "ambient-shift": {
                    "0%, 100%": { backgroundPosition: "0% 50%" },
                    "50%": { backgroundPosition: "100% 50%" },
                },
                "pulse-soft": {
                    "0%, 100%": { transform: "scale(1)", opacity: "0.55" },
                    "50%": { transform: "scale(1.06)", opacity: "1" },
                },
            },
            animation: {
                "ambient-shift": "ambient-shift 14s ease infinite",
                "pulse-soft": "pulse-soft 2s ease-in-out infinite",
            },
        },
    },
    plugins: [],
};
export default config;
