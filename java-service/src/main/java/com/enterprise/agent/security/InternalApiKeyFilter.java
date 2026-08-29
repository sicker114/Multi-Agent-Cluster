package com.enterprise.agent.security;

import cn.hutool.core.util.StrUtil;
import cn.hutool.json.JSONUtil;
import com.enterprise.agent.common.response.R;
import com.enterprise.agent.common.response.ResultCode;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.nio.charset.StandardCharsets;

/**
 * 内部接口密钥过滤器。
 * <p>Python MCP 服务回调 Java 的 {@code /internal/**} 接口（拉取文档、查询业务数据）时，
 * 必须携带内部密钥头 X-Internal-Key，防止内部只读接口被外部滥用。</p>
 *
 * @author enterprise-agent
 */
@Slf4j
@Component
public class InternalApiKeyFilter extends OncePerRequestFilter {

    private static final String HEADER = "X-Internal-Key";

    @Value("${enterprise.internal.api-key:internal-secret-key-2026}")
    private String internalApiKey;

    @Override
    protected void doFilterInternal(HttpServletRequest request,
                                    HttpServletResponse response,
                                    FilterChain filterChain) throws ServletException, IOException {
        String uri = request.getRequestURI();
        if (uri.startsWith("/internal/")) {
            String key = request.getHeader(HEADER);
            if (StrUtil.isBlank(key) || !internalApiKey.equals(key)) {
                log.warn("内部接口非法访问 uri={} key={}", uri, key);
                response.setStatus(HttpServletResponse.SC_FORBIDDEN);
                response.setContentType(MediaType.APPLICATION_JSON_VALUE);
                response.setCharacterEncoding(StandardCharsets.UTF_8.name());
                response.getWriter().write(JSONUtil.toJsonStr(
                        R.failed(ResultCode.ACCESS_DENIED, "内部接口密钥校验失败")));
                return;
            }
        }
        filterChain.doFilter(request, response);
    }
}
