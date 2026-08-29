package com.enterprise.agent.module.auth.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.enterprise.agent.common.exception.BusinessException;
import com.enterprise.agent.common.response.ResultCode;
import com.enterprise.agent.entity.SysUser;
import com.enterprise.agent.mapper.SysUserMapper;
import com.enterprise.agent.module.auth.dto.LoginRequest;
import com.enterprise.agent.module.auth.dto.LoginResponse;
import com.enterprise.agent.module.auth.service.AuthService;
import com.enterprise.agent.security.JwtTokenUtil;
import com.enterprise.agent.security.LoginUser;
import com.enterprise.agent.security.UserDetailsServiceImpl;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;

/**
 * 认证服务实现：校验用户名密码，装配权限，签发 Token。
 *
 * @author enterprise-agent
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class AuthServiceImpl implements AuthService {

    private final SysUserMapper userMapper;
    private final UserDetailsServiceImpl userDetailsService;
    private final PasswordEncoder passwordEncoder;
    private final JwtTokenUtil jwtTokenUtil;

    @Override
    public LoginResponse login(LoginRequest request) {
        SysUser user = userMapper.selectOne(new LambdaQueryWrapper<SysUser>()
                .eq(SysUser::getUsername, request.getUsername()));
        if (user == null || !passwordEncoder.matches(request.getPassword(), user.getPassword())) {
            throw new BusinessException(ResultCode.LOGIN_FAILED);
        }
        if (user.getStatus() == null || user.getStatus() != 1) {
            throw new BusinessException(ResultCode.LOGIN_FAILED, "账号已停用");
        }

        LoginUser loginUser = userDetailsService.buildLoginUser(user);
        String token = jwtTokenUtil.generateToken(user.getUsername(), user.getId(), user.getDeptId());
        log.info("用户登录成功 username={} deptId={} dataScope={}",
                user.getUsername(), user.getDeptId(), loginUser.getDataScope());

        return new LoginResponse(
                token,
                user.getId(),
                user.getUsername(),
                user.getRealName(),
                user.getDeptId(),
                loginUser.getRoleCodes(),
                loginUser.getPermissions());
    }
}
