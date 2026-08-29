package com.enterprise.agent.security;

import com.enterprise.agent.config.EnterpriseProperties;
import io.jsonwebtoken.Claims;
import io.jsonwebtoken.Jwts;
import io.jsonwebtoken.security.Keys;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;

import javax.crypto.SecretKey;
import java.nio.charset.StandardCharsets;
import java.util.Date;
import java.util.HashMap;
import java.util.Map;

/**
 * JWT 工具类：生成 / 解析 / 校验 Token。
 *
 * @author enterprise-agent
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class JwtTokenUtil {

    private static final String CLAIM_USER_ID = "uid";
    private static final String CLAIM_DEPT_ID = "deptId";

    private final EnterpriseProperties properties;

    private SecretKey signKey() {
        return Keys.hmacShaKeyFor(properties.getJwt().getSecret().getBytes(StandardCharsets.UTF_8));
    }

    /**
     * 生成 Token。
     *
     * @param username 用户名
     * @param userId   用户ID
     * @param deptId   部门ID
     * @return JWT 字符串
     */
    public String generateToken(String username, Long userId, Long deptId) {
        Date now = new Date();
        Date expire = new Date(now.getTime() + properties.getJwt().getExpireSeconds() * 1000);
        Map<String, Object> claims = new HashMap<>(4);
        claims.put(CLAIM_USER_ID, userId);
        claims.put(CLAIM_DEPT_ID, deptId);
        return Jwts.builder()
                .claims(claims)
                .subject(username)
                .issuedAt(now)
                .expiration(expire)
                .signWith(signKey())
                .compact();
    }

    /** 解析 Token，非法或过期返回 null。 */
    public Claims parseToken(String token) {
        try {
            return Jwts.parser()
                    .verifyWith(signKey())
                    .build()
                    .parseSignedClaims(token)
                    .getPayload();
        } catch (Exception e) {
            log.warn("解析 Token 失败: {}", e.getMessage());
            return null;
        }
    }

    public String getUsername(Claims claims) {
        return claims.getSubject();
    }

    public Long getUserId(Claims claims) {
        return claims.get(CLAIM_USER_ID, Number.class).longValue();
    }
}
