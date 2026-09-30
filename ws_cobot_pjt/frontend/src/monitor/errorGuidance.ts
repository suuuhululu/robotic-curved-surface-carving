export type ErrorGuidance = {
  severity: "INFO" | "WARNING" | "ERROR";
  action: string;
  retry: "ALLOWED_AFTER_FIX" | "CHECK_CURRENT" | "FORBIDDEN_UNTIL_CONFIRMED";
};

const inputCodes = new Set([
  "INVALID_INPUT",
  "UNSUPPORTED_FORMAT",
  "ASSET_NOT_FOUND",
]);
const currentWorkCodes = new Set(["BUSY", "REQUEST_CONFLICT", "RUN_MISMATCH"]);
const regenerateCodes = new Set([
  "HASH_MISMATCH",
  "PROFILE_MISMATCH",
  "SOURCE_MODE_MISMATCH",
  "UNSUPPORTED_SCHEMA",
  "UNSUPPORTED_SCHEMA_VERSION",
]);
const validationCodes = new Set([
  "VALIDATION_FAILED",
  "VALIDATION_UNAVAILABLE",
  "IK_FAILED",
  "IK_DISCONTINUITY",
  "IK_FK_MISMATCH",
  "JOINT_LIMIT",
  "SINGULARITY_MARGIN",
  "SCENE_REJECTED",
  "PATH_DEVIATION",
]);
const criticalCodes = new Set([
  "FORCE_LIMIT",
  "COMMUNICATION_LOST",
  "STALE_DATA",
  "STOP_UNCONFIRMED",
  "UNKNOWN",
  "TELEMETRY_LOST",
  "GRIP_NOT_CONFIRMED",
  "CONTACT_NOT_FOUND",
  "CONTACT_OUT_OF_RANGE",
  "INVALID_MEASUREMENT",
]);
const motionCodes = new Set([
  "MOTION_NOT_STARTED",
  "MOTION_INCOMPLETE",
  "TIMEOUT",
]);

export function normalizeErrorCode(code?: string | null) {
  if (!code) return "UNKNOWN";
  if (code === "CANCELED") return "CANCELLED";
  return code;
}

export function errorGuidance(code?: string | null): ErrorGuidance {
  const normalized = normalizeErrorCode(code);
  if (normalized === "NONE")
    return {
      severity: "INFO",
      action: "추가 조치 없음",
      retry: "ALLOWED_AFTER_FIX",
    };
  if (inputCodes.has(normalized))
    return {
      severity: "WARNING",
      action: "표시된 필드·파일을 수정한 뒤 모션 없이 다시 요청하세요.",
      retry: "ALLOWED_AFTER_FIX",
    };
  if (currentWorkCodes.has(normalized))
    return {
      severity: "WARNING",
      action: "현재 준비·생성·실행 상태를 확인하고 중복 요청을 만들지 마세요.",
      retry: "CHECK_CURRENT",
    };
  if (regenerateCodes.has(normalized))
    return {
      severity: "ERROR",
      action: "원본·모드·스냅샷을 확인하고 측정과 경로를 새로 생성하세요.",
      retry: "ALLOWED_AFTER_FIX",
    };
  if (validationCodes.has(normalized))
    return {
      severity: "ERROR",
      action: "실행하지 말고 실패 위치·관절·작업영역을 수정한 뒤 재검증하세요.",
      retry: "ALLOWED_AFTER_FIX",
    };
  if (criticalCodes.has(normalized))
    return {
      severity: "ERROR",
      action:
        normalized === "COMMUNICATION_LOST"
          ? "같은 모션을 재전송하지 말고 상태 재확인으로 연결·실제 정지 근거를 확인하세요."
          : "자동 재시도하지 말고 실제 로봇·도구·양초와 정지 상태를 현장에서 확인하세요.",
      retry: "FORBIDDEN_UNTIL_CONFIRMED",
    };
  if (motionCodes.has(normalized))
    return {
      severity: "ERROR",
      action:
        "제어권·현재 위치·실제 정지 상태를 확인하기 전 새 모션을 요청하지 마세요.",
      retry: "FORBIDDEN_UNTIL_CONFIRMED",
    };
  if (normalized === "STORAGE_ERROR")
    return {
      severity: "ERROR",
      action: "저장소를 복구하기 전 새 작업을 요청하지 마세요.",
      retry: "FORBIDDEN_UNTIL_CONFIRMED",
    };
  if (normalized === "NOT_READY")
    return {
      severity: "WARNING",
      action: "표시된 선행 조건과 현재 로봇 상태를 확인하세요.",
      retry: "CHECK_CURRENT",
    };
  if (normalized === "CANCELLED")
    return {
      severity: "WARNING",
      action:
        "최종 정지 결과를 확인한 뒤 필요한 경우 새 작업으로 다시 준비하세요.",
      retry: "CHECK_CURRENT",
    };
  return {
    severity: "ERROR",
    action:
      "알 수 없는 오류입니다. 원문과 현재 상태를 보존하고 새 작업을 시작하지 마세요.",
    retry: "FORBIDDEN_UNTIL_CONFIRMED",
  };
}

export function errorText(code: string | null | undefined, message: string) {
  const normalized = normalizeErrorCode(code);
  const guidance = errorGuidance(normalized);
  return `${normalized} · ${message} · 조치: ${guidance.action}`;
}
