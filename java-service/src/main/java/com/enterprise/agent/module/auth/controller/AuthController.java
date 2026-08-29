package com.enterprise.agent.module.auth.controller;

import com.enterprise.agent.common.annotation.RateLimit;
import com.enterprise.agent.common.response.R;
import com.enterprise.agent.module.auth.dto.LoginRequest;
import com.enterprise.agent.module.auth.dto.LoginResponse;
import com.enterprise.agent.module.auth.service.AuthService;
import com.enterprise.agent.security.LoginUser;
import com.enterprise.agent.security.SecurityUtil;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

import java.util.HashMap;
import java.util.Map;

/**
 * 认证控制器：登录、当前用户信息。
 *
 * @author enterprise-agent
 */
@Tag(name = "认证权限", description = "登录鉴权与当前用户信息")
@RestController
@RequestMapping("/api/auth")
@RequiredArgsConstructor
public class AuthController {

    private final AuthService authService;

    @Operation(summary = "用户登录", description = "校验用户名密码，返回 JWT Token")
    @RateLimit(capacity = 10, refillPerMinute = 10)
    @PostMapping("/login")
    public R<LoginResponse> login(@Valid @RequestBody LoginRequest request) {
        return R.success("登录成功", authService.login(request));
    }

    @Operation(summary = "获取当前登录用户信息")
    @GetMapping("/me")
    public R<Map<String, Object>> currentUser() {
        LoginUser user = SecurityUtil.currentUser();
        Map<String, Object> info = new HashMap<>(8);
        info.put("userId", user.getUserId());
        info.put("username", user.getUsername());
        info.put("realName", user.getUser().getRealName());
        info.put("deptId", user.getDeptId());
        info.put("roles", user.getRoleCodes());
        info.put("permissions", user.getPermissions());
        info.put("dataScope", user.getDataScope());
        return R.success(info);
    }
}
