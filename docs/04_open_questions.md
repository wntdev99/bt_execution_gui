# 04. Open Questions — 결정 미확정 사항

> **역할:** v1 설계 합의 후에도 결정이 미뤄진 사항 박제. 구현 진행 중 단계적으로 결정 → 본 문서에 결정 반영 후 SSOT 문서들로 승격.
>
> **승격 규칙:** 한 항목이 결정되면 (1) 본 문서의 항목에 `[결정: ...]` 추가, (2) 영향 SSOT 문서 갱신, (3) Git commit log 에 사유 기록.

---

## A. 데이터 / 영속성

### A-1. 시나리오 yaml schema_version 1 의 향후 마이그레이션

**상태:** 미결정.
**고려:**
- v1 의 schema_version 필드는 1.
- 향후 step kind 추가 (조건 분기, nested 등) 시 schema_version 증가.
- 백엔드는 자동 마이그레이션 vs 거부 후 사용자 마이그레이션 도구 제공?
**제안:** 자동 마이그레이션 + git history 보존. v1 → v2 시 in-place 변환.

### A-2. 실행 이력 sqlite 보존 정책

**상태:** 가설로 "최근 500 실행 유지" 제안. 미확정.
**고려:**
- 사용자가 며칠 전 실행 결과를 디버깅에 보고 싶을 수 있음 — 500 너무 적음?
- B-33 (mock 한계) 의 영향으로 실 환경 실행 이력의 가치 큼.
- 디스크: 500 실행 × ~5KB = 2.5MB. 충분.
**제안:** 5000 실행 또는 90 일 중 짧은 쪽. 사용자 결정 필요.

### A-3. snapshot_json 의 BB 상태 dump 깊이

**상태:** 미결정.
**고려:**
- 시나리오 실패 시 마지막 BB 상태를 dump 하면 사후 분석에 가치.
- bt_execution_server 의 SqliteLogger 가 별도 .db3 생성 — bt_web_bridge 가 이를 참조?
- bt_execution_server.cpp 의 SqliteLogger 가 `main_succeeded`/`param_status`/`door_open`/`zone_aware_paused` 4 키만 dump.
**제안:** v1 은 step 단위 result_message 만. v2 에서 .db3 download 링크 제공.

---

## B. UI / UX

### B-1. PoseStamped 입력 — 지도 클릭 vs 숫자 input

**상태:** 미결정. v1 은 숫자 input 만.
**고려:**
- 지도 클릭은 rviz 같은 별도 도구 사용 또는 leaflet 등 web map 임베드.
- 좌표계 (map frame) 시각화 필요.
- v1 은 숫자 only 로 시작, v2 에서 지도 위젯 도입 검토.
**제안:** v1 = 숫자 input. payload preset 기능으로 미리 저장된 pose 재사용 (B-3 참조).

### B-2. 카드 정렬/필터/즐겨찾기

**상태:** 미결정.
**고려:**
- v1 트리 6 개라 필터 불필요? 추후 트리 수 증가 시 필요.
- 즐겨찾기는 사용자별 vs 글로벌? 사내망 신뢰 → 글로벌이면 충분.
**제안:** v1 = 카테고리 필터(single/scenario_step) + 즐겨찾기 글로벌. 검색은 v2.

### B-3. payload preset 저장

**상태:** 미결정.
**고려:**
- 자주 쓰는 payload (예: "backward_dock 도킹") 를 preset 으로 저장 → 카드 클릭 시 preset 선택.
- 시나리오와 차이: preset 은 단일 트리, 시나리오는 다중.
**제안:** v2 기능. 임시로는 시나리오 1-step 시나리오로 우회 가능.

### B-4. 다국어 (한국어 / 영어)

**상태:** v1 = 한국어 only.
**고려:**
- BT 함정 (B-22, B-30 등) 의 note 가 한국어 작성됨.
- 향후 외부 노출 시 i18n 필요할 수 있음.
**제안:** v1 = 한국어. 코드 i18n 인프라(next-intl)는 사전 구비, 영어 번역은 v2.

### B-5. Theme

**상태:** v1 = light only (토스풍).
**제안:** v2 = dark mode 추가. Tailwind 의 dark class 만 적용하면 비용 적음.

### B-6. Mobile responsive

**상태:** v1 = 데스크탑 우선.
**고려:** 시나리오 빌더 UX 가 모바일에서 어려움. 단일 실행은 가능.
**제안:** v1 = 데스크탑 + 태블릿 (≥768px). 모바일은 v2.

### B-7. 실시간 feedback 깊이

**상태:** v1 = string message only (BT feedback).
**고려:**
- BT.CPP 의 SqliteLogger db3 다운로드 — 사후 분석 강력하지만 UX 복잡.
- BB key 변화 (예: `number_recoveries` 증가) 실시간 표시 가치 있음.
**제안:** v1 = string message. v2 에서 (선택) feedback panel 에 BB key watch 기능.

### B-8. 시나리오 빌더의 visualization 라이브러리

**상태:** react-flow vs SVG 자체 vs react-archer 미결정.
**고려:**
- react-flow: 강력하지만 무거움. 노드 편집 까지 지원.
- SVG 자체: 라이트하지만 화살표 라우팅 직접 구현.
- react-archer: 화살표만 — 가장 가볍.
**제안:** linear 시퀀스만이라 react-archer + dnd-kit 조합 충분. v2 에서 분기 도입 시 react-flow.

### B-9. 사용자 친화적 에러 메시지 매트릭스

**상태:** 미결정.
**고려:** `develop_bt/guide/06_error_codes_reference.md` §11.5 의 substring → 한국어 친화 메시지 매핑 필요.
**예시:**
- `Missing key [tf_buffer]` → "TF buffer 미설정 (개발자 문의)"
- `Invalid service name: topic name must not be empty string` → "service_name BB key 가 비어있음 (payload 누락)"
**제안:** v1 에서 매트릭스 작성 + UI 에 적용. `error_message_mapper.py` 모듈.

---

## C. DevOps

### C-1. systemd unit 작성

**상태:** 결정 (배포 형태) ✅. 구현 단계 미정.
**구현 항목:**
```
[Unit]
Description=bt_web_bridge
After=network.target ros2.target

[Service]
Type=simple
User=robot
Environment="ROS_DOMAIN_ID=..."
WorkingDirectory=/home/robot/ros2_ws
ExecStart=/bin/bash -c "source install/setup.bash && ros2 run bt_web_bridge bt_web_bridge"
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### C-2. dev-behavior-tree ↔ bt_execution_gui 호환성

**상태:** 미결정.
**고려:**
- bt_schema_server 의 srv 인터페이스 변경 시 buddy-version 필요.
- README 에 호환 매트릭스 박제?
**제안:** semantic versioning. bt_execution_gui v1.x ↔ bt_schema_server srv v1.x. 변경 시 마이너 버전 bump 및 호환 표 갱신.

### C-3. CI / GitHub Actions

**상태:** 미결정.
**제안:**
- bt_execution_gui: Python lint (ruff) + TS lint + 빌드.
- 통합: dev-behavior-tree clone + colcon build + bt_schema_server 띄우고 self-check 실행.
- CI 환경에서 ROS2 가 필요 → ros:jazzy 컨테이너.

### C-4. ROS2 domain id 분리

**상태:** 미결정.
**고려:** 운영/개발 머신 분리 가능.
**제안:** systemd unit 환경변수로 `ROS_DOMAIN_ID` 명시. 운영=42, 개발=0 등.

### C-5. 로깅 / 모니터링

**상태:** 미결정.
**제안:** v1 = stdout + journalctl. v2 = Loki/Grafana 옵션.

### C-6. 테스트 전략

**상태:** 미결정.
**제안:**
- bt_web_bridge: pytest + mock ROS bridge.
- payload_validator: 단위 테스트 (manifest fixture).
- self_check: integration test (mock bt_schema_server srv).
- Frontend: vitest (단위) + playwright (e2e).

---

## D. 기능 확장 (v2+)

### D-1. 시나리오 내 조건 분기

**상태:** v1 제외. 결정.
**고려:** "도킹 실패 시 재시도 3 회" 같은 패턴 — BT 자체에서 처리 가능 (RecoveryNode). 시나리오 빌더에서 추가하면 중복 가능.
**제안:** BT 자체 분기 우선. 시나리오는 linear 유지. v2 에서 재검토.

### D-2. Nested 시나리오 (시나리오 in 시나리오)

**상태:** v1 제외. 결정.
**고려:** yaml 간 참조 + cycle 검증 + 재귀 실행. 복잡도 큼.
**제안:** v2 에서 도입 결정.

### D-3. 시나리오 dry-run (실행 없이 검증)

**상태:** 미결정.
**고려:** Layer 4 검증을 명시적 endpoint 로? `POST /api/scenarios/{id}/validate` 추가.
**제안:** v1 에 포함 — 비용 작음.

### D-4. 시나리오 export / import (yaml 파일)

**상태:** 미결정.
**고려:** 시나리오가 git tracked yaml 이라 git 으로도 가능. UI 에서 직접 다운로드/업로드 편의 기능.
**제안:** v1 에 포함 — 비용 작음.

---

## E. 안전 / 보안 (v1 미포함)

### E-1. 위험 액션 confirm 모달

**상태:** v1 제외. 결정.
**고려:** manifest 의 `dangerous: true` 플래그는 정의됨. UI 단순화 위해 v1 제외.
**제안:** v2 에서 도입. 현재는 사용자 신중 운영 + Emergency Stop 으로 대응.

### E-2. 로봇 사전 상태 점검

**상태:** v1 제외. 결정.
**고려:**
- nav2 lifecycle / battery / e-stop 사전 확인 가치 큼.
- ROS 상태 구독 인프라 추가 필요.
**제안:** v2 에서 도입. 별도 status panel.

### E-3. 인증 (Bearer token / OAuth)

**상태:** v1 제외. 결정 (사내망 신뢰).
**제안:** 외부 노출 시 v2 에서 Bearer token 1 단계 도입.

### E-4. 백엔드 재시작 시 in-flight goal cleanup

**상태:** 미결정.
**고려:**
- bt_web_bridge 다운 시 nav2 가 마지막 goal 진행 중일 수 있음 → 위험.
- 재시작 시 마지막 active_goal_uuid 를 sqlite 에서 복구 + cancel 시도?
**제안:** v1 에 포함. `lock_manager.py` 의 startup 단계에 추가.

---

## F. Schema 추출 한계 회귀 (v2)

### F-1. bt_schema_server 옵션 2 (dryrun mode) 회귀

**상태:** v1 = 옵션 1 (createTree 안 함) 만 사용.
**회귀 트리거:**
- 옵션 1 의 80~95% 추출이 운영에서 부족하다고 판단 시.
- 예: `getInputOrBlackboard` fallback 노드가 너무 많아 manifest 누락 빈발.
**제안:** behaviortree_ros2 에 `RosNodeParams::wait_for_server_timeout` 추가 PR + 옵션 2 모드 추가.

### F-2. BT.CPP scripting 파서 정밀도

**상태:** v1 = 단순 식만.
**고려:** 복합 식 (`a && b == c`) 의 변수 추출 보수적 처리. False positive 발생 시 manifest 의 `explicit_exclude` 키로 보완?
**제안:** 운영 중 false positive 빈도 측정 → 필요 시 파서 보강.

---

## 결정 트리거 매트릭스

| Open Question | 결정 시점 | 영향 SSOT 갱신 |
|---|---|---|
| A-1 schema version 마이그레이션 | v2 시작 시 | scenario_storage.py + 본 문서 |
| A-2 이력 보존 정책 | 첫 운영 1 주 후 | history_db.py + 본 문서 |
| B-9 에러 메시지 매트릭스 | v1 구현 중 | bt_web_bridge/error_message_mapper.py + 본 문서 |
| C-1 systemd unit | 첫 배포 직전 | docs/deployment.md (신규) + 본 문서 |
| C-2 호환 매트릭스 | 첫 release tag | README + 본 문서 |
| D-3 시나리오 dry-run | 폼 검증 endpoint 구현 시 | 03_api_protocol.md + 본 문서 |
| D-4 export/import | UI 첫 cut 후 | 03_api_protocol.md + 본 문서 |
| E-4 in-flight cleanup | v1 lock_manager 구현 시 | 01_system_design.md §2.3 + 본 문서 |

---

## 결정 이력 (Decision Log)

| 일자 | 결정 사항 | 사유 |
|---|---|---|
| 2026-05-21 | 백엔드 Python+rclpy+FastAPI | 사용자 결정. ROS2 colcon 생태계 일관 |
| 2026-05-21 | 프론트엔드 Next.js+shadcn | 사용자 결정. 토스 디자인 + 시나리오 빌더 UX |
| 2026-05-21 | 트리 메타데이터 sidecar yaml | 사용자 결정. dev-behavior-tree repo 내 트리별 .meta.yaml |
| 2026-05-21 | 시나리오=yaml + 이력=sqlite | 사용자 결정 |
| 2026-05-21 | 4-Layer Defense (Layer 2 별도 노드) | 사용자 결정. zero-error 보장 |
| 2026-05-21 | 배포 colcon+systemd | 사용자 결정. dev-behavior-tree workspace 호환 |
| 2026-05-21 | 인증 사내망 신뢰 + CORS | 사용자 결정 (v1) |
| 2026-05-21 | 시나리오 linear + Pause/Step-by-step (액션 경계) | 사용자 결정. BT mid-tick pause 불가 한계 박제 |
| 2026-05-21 | 안전 = E-STOP 만 (v1) | 사용자 결정. confirm 모달/사전 점검은 v2 |
