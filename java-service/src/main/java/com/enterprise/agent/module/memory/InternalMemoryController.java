package com.enterprise.agent.module.memory;

import com.enterprise.agent.common.response.R;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.Data;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

import java.util.HashMap;
import java.util.Map;

/**
 * 内部记忆读写接口（供 Python 记忆工具通过 Redis 之外的受控通道共享长期记忆）。
 * <p>由 InternalApiKeyFilter 保护，按 userId 隔离。Python 通过此接口复用历史问答，
 * 减少重复 LLM 调用。</p>
 *
 * @author enterprise-agent
 */
@Tag(name = "内部记忆接口", description = "供 Python 共享四层记忆的长期记忆层")
@RestController
@RequestMapping("/internal/memory")
@RequiredArgsConstructor
public class InternalMemoryController {

    private final MemoryManager memoryManager;

    @Operation(summary = "读取长期记忆命中")
    @GetMapping("/longterm")
    public R<Map<String, Object>> getLongTerm(@RequestParam Long userId,
                                              @RequestParam String question) {
        Object hit = memoryManager.hitLongTermCache(userId, question);
        Map<String, Object> result = new HashMap<>(2);
        result.put("hit", hit != null);
        result.put("value", hit);
        return R.success(result);
    }

    @Operation(summary = "写入长期记忆问答报告")
    @PostMapping("/longterm")
    public R<Void> saveLongTerm(@RequestBody SaveMemoryRequest req) {
        memoryManager.saveLongTermQa(req.getUserId(), req.getQuestion(), req.getValue());
        return R.success();
    }

    @Operation(summary = "记录幻觉错误案例")
    @PostMapping("/hallucination")
    public R<Void> saveHallucination(@RequestBody SaveMemoryRequest req) {
        memoryManager.saveHallucinationCase(req.getUserId(), req.getQuestion(), req.getValue());
        return R.success();
    }

    @Data
    public static class SaveMemoryRequest {
        private Long userId;
        private String question;
        private Object value;
    }
}
