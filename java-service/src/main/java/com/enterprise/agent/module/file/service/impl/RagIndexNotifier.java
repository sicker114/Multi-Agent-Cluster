package com.enterprise.agent.module.file.service.impl;

import cn.hutool.core.util.StrUtil;
import cn.hutool.http.HttpRequest;
import cn.hutool.http.HttpResponse;
import cn.hutool.json.JSONUtil;
import com.enterprise.agent.config.EnterpriseProperties;
import com.enterprise.agent.entity.BizDocument;
import com.enterprise.agent.mapper.BizDocumentMapper;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Component;

import java.util.LinkedHashMap;
import java.util.Map;

/**
 * GraphRAG 异步入库通知组件。
 * <p>文档上传 / 标记删除后，通过 Python MCP 暴露的 HTTP 内部接口
 * （{@code POST /internal/rag/index-doc} 与 {@code POST /internal/rag/delete-doc}）
 * 触发 GraphRAG 的 Chroma 索引增量构建或按 docId 删除。
 * 执行完全异步：HTTP 失败不影响主接口，文档状态自动记录 {@code indexed} 字段。</p>
 *
 * @author enterprise-agent
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class RagIndexNotifier {

    private final EnterpriseProperties properties;
    private final BizDocumentMapper documentMapper;

    /**
     * 异步通知 Python GraphRAG 侧构建单个文档索引。
     *
     * @param docId  文档ID
     * @param deptId 部门ID（用于数据权限过滤）
     */
    @Async
    public void notifyIndex(Long docId, Long deptId) {
        if (docId == null) return;
        // 先写入"索引中"状态(2)，成功后置1，失败置3
        updateIndexed(docId, 2);
        String url = indexEndpoint("/internal/rag/index-doc");
        Map<String, Object> body = new LinkedHashMap<>(4);
        body.put("docId", docId);
        body.put("deptId", deptId);
        try {
            boolean ok = postInternal(url, body);
            updateIndexed(docId, ok ? 1 : 3);
            log.info("GraphRAG 入库通知 docId={} ok={}", docId, ok);
        } catch (Exception e) {
            log.warn("GraphRAG 入库通知失败 docId={} err={}", docId, e.getMessage());
            updateIndexed(docId, 3);
        }
    }

    /**
     * 异步通知 Python GraphRAG 侧删除指定文档向量片段。
     *
     * @param docId 文档ID
     */
    @Async
    public void notifyDelete(Long docId) {
        if (docId == null) return;
        String url = indexEndpoint("/internal/rag/delete-doc");
        Map<String, Object> body = new LinkedHashMap<>(2);
        body.put("docId", docId);
        try {
            boolean ok = postInternal(url, body);
            log.info("GraphRAG 删除通知 docId={} ok={}", docId, ok);
        } catch (Exception e) {
            log.warn("GraphRAG 删除通知失败 docId={} err={}", docId, e.getMessage());
        }
    }

    private String indexEndpoint(String path) {
        // P0+ 双通道：Python GraphRAG/索引地址统一从 mcp.pythonBaseUrl 取，
        // 仍保留 PYTHON_MCP_BASE_URL 环境变量作部署期覆写。
        String base = properties.getMcp().getPythonBaseUrl();
        String override = System.getenv("PYTHON_MCP_BASE_URL");
        String hostPrefix = StrUtil.blankToDefault(override, base);
        if (hostPrefix.endsWith("/") && path.startsWith("/")) {
            hostPrefix = hostPrefix.substring(0, hostPrefix.length() - 1);
        }
        return hostPrefix + path;
    }

    private boolean postInternal(String url, Map<String, Object> body) {
        long timeout = properties.getInternal().getHttpTimeoutMs();
        try (HttpResponse resp = HttpRequest.post(url)
                .header("X-Internal-Key", properties.getInternal().getApiKey())
                .body(JSONUtil.toJsonStr(body))
                .timeout((int) timeout)
                .execute()) {
            if (resp.getStatus() != 200) {
                log.warn("GraphRAG 内部回调异常 url={} status={} body={}", url, resp.getStatus(), resp.body());
                return false;
            }
            return true;
        }
    }

    private void updateIndexed(Long docId, int status) {
        try {
            BizDocument doc = new BizDocument();
            doc.setId(docId);
            doc.setIndexed(status);
            documentMapper.updateById(doc);
        } catch (Exception e) {
            log.warn("更新文档 indexed 字段失败 docId={} status={} err={}", docId, status, e.getMessage());
        }
    }
}
