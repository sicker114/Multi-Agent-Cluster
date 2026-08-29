package com.enterprise.agent.security;

import cn.hutool.json.JSONUtil;
import com.enterprise.agent.common.response.R;
import com.enterprise.agent.common.response.ResultCode;
import jakarta.servlet.http.HttpServletResponse;
import lombok.RequiredArgsConstructor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.MediaType;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.config.annotation.authentication.configuration.AuthenticationConfiguration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;

import java.nio.charset.StandardCharsets;

/**
 * Spring Security 配置：无状态 JWT + RBAC 方法级权限。
 * <p>放行登录、文档、Knife4j、供 Python 拉取的内部接口；其余接口需鉴权。</p>
 *
 * @author enterprise-agent
 */
@Configuration
@EnableMethodSecurity      // 开启 @PreAuthorize 方法级 RBAC
@RequiredArgsConstructor
public class SecurityConfig {

    private final JwtAuthenticationFilter jwtAuthenticationFilter;
    private final InternalApiKeyFilter internalApiKeyFilter;

    /** 放行路径：登录、文档、静态前端资源、内部拉取接口（Python 通过独立密钥头访问）。 */
    private static final String[] WHITE_LIST = {
            "/api/auth/login",
            "/doc.html", "/webjars/**", "/v3/api-docs/**", "/swagger-ui/**", "/swagger-resources/**",
            "/favicon.ico", "/error",
            // 前端静态资源（SPA 入口与资源）
            "/", "/index.html", "/css/**", "/js/**", "/assets/**", "/static/**"
    };

    @Bean
    public SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http
                .csrf(csrf -> csrf.disable())
                .cors(cors -> {
                })
                .sessionManagement(sm -> sm.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(WHITE_LIST).permitAll()
                        // 内部接口：供 Python MCP 服务回调拉取文档与数据，由独立 InternalApiKeyFilter 校验
                        .requestMatchers("/internal/**").permitAll()
                        .anyRequest().authenticated())
                .exceptionHandling(ex -> ex
                        .authenticationEntryPoint((request, response, e) ->
                                writeJson(response, HttpServletResponse.SC_UNAUTHORIZED,
                                        R.failed(ResultCode.UNAUTHORIZED)))
                        .accessDeniedHandler((request, response, e) ->
                                writeJson(response, HttpServletResponse.SC_FORBIDDEN,
                                        R.failed(ResultCode.ACCESS_DENIED))))
                .addFilterBefore(internalApiKeyFilter, UsernamePasswordAuthenticationFilter.class)
                .addFilterBefore(jwtAuthenticationFilter, UsernamePasswordAuthenticationFilter.class);
        return http.build();
    }

    private void writeJson(HttpServletResponse response, int status, R<?> body) throws java.io.IOException {
        response.setStatus(status);
        response.setContentType(MediaType.APPLICATION_JSON_VALUE);
        response.setCharacterEncoding(StandardCharsets.UTF_8.name());
        response.getWriter().write(JSONUtil.toJsonStr(body));
    }

    @Bean
    public PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    public AuthenticationManager authenticationManager(AuthenticationConfiguration config) throws Exception {
        return config.getAuthenticationManager();
    }
}
