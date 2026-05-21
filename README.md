# bt_execution_gui

Behavior Tree (BT) execution 을 위한 운영 GUI. ROS2 머신 위에서 동작하는 web 브릿지 + Next.js 프론트엔드.

> **상태:** 설계 단계 (2026-05-21). 구현 전 합의된 SSOT 는 [`docs/`](docs/) 참조.

---

## 빠른 시작

설계 문서부터 읽으십시오:

1. **[`docs/README.md`](docs/README.md)** — 개요 + 메타 원칙 + 결정 사항 + 토폴로지
2. **[`docs/01_system_design.md`](docs/01_system_design.md)** — 백엔드/프론트엔드/데이터 모델/시나리오 엔진
3. **[`docs/02_schema_extraction.md`](docs/02_schema_extraction.md)** — 4-Layer Defense + bt_schema_server
4. **[`docs/03_api_protocol.md`](docs/03_api_protocol.md)** — HTTP REST + WebSocket 명세
5. **[`docs/04_open_questions.md`](docs/04_open_questions.md)** — 결정 미확정 사항

---

## 핵심 결정 사항 (2026-05-21)

| 항목 | 결정 |
|---|---|
| 백엔드 | Python + rclpy + FastAPI |
| 프론트엔드 | Next.js 14 + TS + Tailwind + shadcn |
| 트리 메타데이터 | 트리별 sidecar `.meta.yaml` (각 트리 옆) |
| 시나리오 저장 | yaml (시나리오) + sqlite (이력) |
| Schema 추출 | 4-Layer Defense |
| Layer 2 | 별도 `bt_schema_server` ROS2 노드 |
| 배포 | colcon package + systemd service |
| 인증 | 사내망 신뢰 + CORS 제한 (v1) |
| 시나리오 빌더 | Linear + 대기 + Pause/Step-by-step (액션 경계 한정) |
| 안전 | 전역 Emergency Stop 버튼 |

---

## 관련 Repo

- [`dev-behavior-tree`](https://github.com/...) — BT 작성 SSOT. `behavior_trees/*.xml` + `develop_bt/guide/` + (예정) `bt_schema_server` 패키지 + `behavior_trees/*.meta.yaml`.

본 repo (`bt_execution_gui`) 는 dev-behavior-tree 에 의존하지만, dev-behavior-tree 는 본 repo 에 의존하지 않습니다 (단방향).
