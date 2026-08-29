package com.enterprise.agent.security;

import cn.hutool.core.util.StrUtil;
import com.enterprise.agent.config.EnterpriseProperties;
import io.jsonwebtoken.Claims;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import lombok.RequiredArgsConstructor;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.web.authentication.WebAuthenticationDetailsSource;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;

/**
 * JWT 鉴权过滤器：从请求头解析 Token，校验通过后装配 SecurityContext。
 *
 * @author enterprise-agent
 */
@Component
@RequiredArgsConstructor
public class JwtAuthenticationFilter extends OncePerRequestFilter {

    private final JwtTokenUtil jwtTokenUtil;
    private final EnterpriseProperties properties;
    private final UserDetailsServiceImpl userDetailsService;

    @Override
    protected void doFilterInternal(HttpServletRequest request,
                                    HttpServletResponse response,
                                    FilterChain filterChain) throws ServletException, IOException {
        String header = request.getHeader(properties.getJwt().getHeader());
        String prefix = properties.getJwt().getPrefix();

        if (StrUtil.isNotBlank(header) && header.startsWith(prefix)) {
            String token = header.substring(prefix.length());
            Claims claims = jwtTokenUtil.parseToken(token);
            if (claims != null && SecurityContextHolder.getContext().getAuthentication() == null) {
                String username = jwtTokenUtil.getUsername(claims);
                LoginUser loginUser = (LoginUser) userDetailsService.loadUserByUsername(username);
                UsernamePasswordAuthenticationToken authentication =
                        new UsernamePasswordAuthenticationToken(
                                loginUser, null, loginUser.getAuthorities());
                authentication.setDetails(new WebAuthenticationDetailsSource().buildDetails(request));
                SecurityContextHolder.getContext().setAuthentication(authentication);
            }
        }
        filterChain.doFilter(request, response);
    }
}
