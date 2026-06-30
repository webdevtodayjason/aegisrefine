Operate an Aegis Refine demo job using the aegis-refine skill.

Context:
- Product: Aegis Refine
- Live URL: https://aegisrefine.com
- Hermes Agent role: operator/runtime
- Operations brain: nvidia/nemotron-3-ultra-550b-a55b
- Latency fallback: nvidia/nemotron-3-nano-30b-a3b
- Safety gate: nvidia/nemotron-3.5-content-safety for PII / unsafe-content review
- Data-governance specialist: Aegis-14B, trained from Hermes 14B
- Infrastructure: clustered NVIDIA DGX Spark via AInode
- Money rail: Stripe capped Checkout for earned revenue; outbound spend is an internal cap ledger/test stub unless a Stripe payment intent is attached
- Proof: signed AAR certificate and admin receipt

Task:
1. Check production Aegis-14B health.
2. Produce the operator decision JSON from the skill, including the actual active model and safety_gate status.
3. Summarize the route in 3 sentences for a hackathon demo.
4. Be explicit about anything unverified.
