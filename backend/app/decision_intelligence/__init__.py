"""Phase 15: Decision Intelligence -- an additive composition layer over
Phase 11 (project-level prediction + live SHAP + grounded RAG evidence +
contradiction context + what-if scenario) and Phase 14 (portfolio
prediction cache + portfolio risk scoring + peer-group analytics +
portfolio-wide SHAP drivers). See docs/DECISION_INTELLIGENCE.md.

Nothing in this package retrains, refits, or reloads a model; recomputes
Phase 8 embeddings/FAISS; reruns Phase 9 contradiction detection; or
triggers Phase 14 batch scoring. Every number surfaced here is read from an
existing Phase 11/14 service, called as a black box.
"""
