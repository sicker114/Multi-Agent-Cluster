package com.enterprise.agent.security;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.enterprise.agent.entity.SysRole;
import com.enterprise.agent.entity.SysUser;
import com.enterprise.agent.mapper.SysPermissionMapper;
import com.enterprise.agent.mapper.SysRoleMapper;
import com.enterprise.agent.mapper.SysUserMapper;
import lombok.RequiredArgsConstructor;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.stereotype.Service;

import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;

/**
 * Spring Security 用户加载服务：根据用户名装配 {@link LoginUser}（角色、权限、数据范围）。
 *
 * @author enterprise-agent
 */
@Service
@RequiredArgsConstructor
public class UserDetailsServiceImpl implements UserDetailsService {

    private final SysUserMapper userMapper;
    private final SysRoleMapper roleMapper;
    private final SysPermissionMapper permissionMapper;

    @Override
    public UserDetails loadUserByUsername(String username) throws UsernameNotFoundException {
        SysUser user = userMapper.selectOne(new LambdaQueryWrapper<SysUser>()
                .eq(SysUser::getUsername, username));
        if (user == null) {
            throw new UsernameNotFoundException("用户不存在");
        }
        return buildLoginUser(user);
    }

    /**
     * 装配登录主体：角色、权限标识、数据范围。
     * <p>数据范围取所有角色中最大范围（1 全部优先于 2 本部门）。</p>
     */
    public LoginUser buildLoginUser(SysUser user) {
        List<SysRole> roles = roleMapper.selectRolesByUserId(user.getId());
        Set<String> roleCodes = roles.stream()
                .map(SysRole::getRoleCode)
                .collect(Collectors.toCollection(HashSet::new));

        // 数据范围：只要拥有任一全量范围角色，即视为全量
        int dataScope = roles.stream()
                .map(SysRole::getDataScope)
                .min(Integer::compareTo)
                .orElse(2);

        Set<String> permissions = new HashSet<>(permissionMapper.selectPermCodesByUserId(user.getId()));
        return new LoginUser(user, roleCodes, permissions, dataScope);
    }
}
