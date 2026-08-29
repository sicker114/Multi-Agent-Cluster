package com.enterprise.agent.module.auth.service;

import com.enterprise.agent.module.auth.dto.LoginRequest;
import com.enterprise.agent.module.auth.dto.LoginResponse;

/**
 * 认证服务接口。
 *
 * @author enterprise-agent
 */
public interface AuthService {

    /**
     * 用户登录，校验密码并签发 JWT。
     *
     * @param request 登录请求
     * @return 登录响应
     */
    LoginResponse login(LoginRequest request);
}
