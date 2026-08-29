package com.enterprise.agent.module.auth.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.util.Set;

/**
 * 登录响应，包含 Token 与用户基础信息。
 *
 * @author enterprise-agent
 */
@Data
@NoArgsConstructor
@AllArgsConstructor
@Schema(description = "登录响应")
public class LoginResponse {

    @Schema(description = "JWT Token")
    private String token;

    @Schema(description = "用户ID")
    private Long userId;

    @Schema(description = "用户名")
    private String username;

    @Schema(description = "真实姓名")
    private String realName;

    @Schema(description = "部门ID")
    private Long deptId;

    @Schema(description = "角色编码集合")
    private Set<String> roles;

    @Schema(description = "权限标识集合")
    private Set<String> permissions;
}
