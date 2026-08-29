package com.enterprise.agent.module.business.controller;

import com.enterprise.agent.common.response.R;
import com.enterprise.agent.module.business.dto.SafeQueryRequest;
import com.enterprise.agent.module.business.service.BusinessDataService;
import com.enterprise.agent.module.file.service.DocumentService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

/**
 * 内部回调接口（供 Python MCP 服务的子 Agent 调用）。
 * <p>由 {@code InternalApiKeyFilter} 通过 X-Internal-Key 密钥头保护。
 * 提供：文档正文拉取（GraphRAG Agent）、文档清单、业务数据安全查询（SQL Agent）。</p>
 *
 * @author enterprise-agent
 */
@Tag(name = "内部回调接口", description = "供 Python 子 Agent 拉取文档与只读业务数据")
@RestController
@RequestMapping("/internal")
@RequiredArgsConstructor
public class InternalCallbackController {

    private final DocumentService documentService;
    private final BusinessDataService businessDataService;

    @Operation(summary = "拉取文档正文（脱敏）", description = "GraphRAG Agent 构建知识图谱使用")
    @GetMapping("/doc/{docId}/content")
    public R<Map<String, Object>> docContent(@PathVariable Long docId) {
        return R.success(documentService.readContentForAgent(docId));
    }

    @Operation(summary = "列出部门文档清单")
    @GetMapping("/doc/list")
    public R<List<Map<String, Object>>> docList(@RequestParam(required = false) Long deptId) {
        return R.success(documentService.listDocsForAgent(deptId));
    }

    @Operation(summary = "业务数据安全查询", description = "SQL Agent 只读统计查询，含高危 SQL 拦截")
    @PostMapping("/data/query")
    public R<List<Map<String, Object>>> query(@RequestBody SafeQueryRequest request) {
        return R.success(businessDataService.safeQuery(request));
    }
}
