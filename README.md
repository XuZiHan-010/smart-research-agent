# Smart Research Agent / 智能市场研究助手

![Python](https://img.shields.io/badge/Python-3.12-blue) ![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-brightgreen) ![React](https://img.shields.io/badge/React-18-61dafb?logo=react) ![LangGraph](https://img.shields.io/badge/LangGraph-multi--agent-orange) ![Railway](https://img.shields.io/badge/Railway-deployed-blueviolet)

基于多智能体 LangGraph 流水线，自动生成深度中文市场研究报告，支持实时流式输出与多格式导出。

AI-powered market research platform that auto-generates in-depth Chinese reports via a multi-agent LangGraph pipeline with real-time SSE streaming and multi-format export.

## 核心功能 / Features

- **并行主题研究** — 同时执行市场规模、竞争格局、政策、技术趋势等 7 大维度研究 / *Parallel multi-theme research across 7 dimensions (market size, competitive landscape, policy, tech trends, etc.) running concurrently*

- **质量守门员** — 每个主题报告自动评估引用数、篇幅、实体覆盖度，失败自动重试；采用 Exa 神经搜索获取真实网络文献 / *Quality-gated ThemeSubAgents: auto-retry on citation/length/entity failures; real web docs fetched via Exa neural search*

- **交叉验证** — 跨主题冲突检测和引用空白填补 / *Cross-theme conflict detection and citation-gap filling via Gemini 2.5 Flash*

- **流式编辑器** — GPT-4.1 实时撰写最终报告，前端 SSE 流式显示；支持 Markdown / PDF（CJK 字体）/ Word 导出 / *Streaming GPT-4.1 editor with real-time SSE display; export to Markdown, PDF (CJK-aware), or Word*

## 技术栈 / Tech Stack

| 层次 | 技术 |
|------|------|
| **后端 / Backend** | Python 3.12, FastAPI, LangGraph, LangChain, Motor (async MongoDB) |
| **前端 / Frontend** | React 18, TypeScript, Vite, Tailwind CSS, Framer Motion |
| **AI 模型 / AI Models** | GPT-4.1 (report writer, editor), GPT-4.1-mini (query gen), Gemini 2.5 Flash (validator) |
| **网络检索 / Search** | Exa Neural Search API |
| **数据库 / Database** | MongoDB |
| **部署 / Deployment** | Railway, Docker (multi-stage build), Gunicorn + Uvicorn |
