package com.enterprise.agent.security;

import com.enterprise.agent.entity.SysUser;
import lombok.Getter;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.userdetails.UserDetails;

import java.util.Collection;
import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;
import java.util.stream.Stream;

/**
 * Spring Security 登录用户主体，封装用户、角色编码、权限标识与数据权限范围。
 *
 * @author enterprise-agent
 */
@Getter
public class LoginUser implements UserDetails {

    private final SysUser user;

    /** 角色编码集合，如 ADMIN / EMPLOYEE。 */
    private final Set<String> roleCodes;

    /** 权限标识集合，如 analysis:ask。 */
    private final Set<String> permissions;

    /** 数据范围：1 全部数据；2 本部门数据。 */
    private final Integer dataScope;

    public LoginUser(SysUser user, Set<String> roleCodes, Set<String> permissions, Integer dataScope) {
        this.user = user;
        this.roleCodes = roleCodes;
        this.permissions = permissions;
        this.dataScope = dataScope;
    }

    public Long getUserId() {
        return user.getId();
    }

    public Long getDeptId() {
        return user.getDeptId();
    }

    @Override
    public Collection<? extends GrantedAuthority> getAuthorities() {
        // 角色以 ROLE_ 前缀，权限标识原样，二者合并为 Spring Security 授权集
        return Stream.concat(
                        roleCodes.stream().map(r -> "ROLE_" + r),
                        permissions.stream())
                .map(SimpleGrantedAuthority::new)
                .collect(Collectors.toList());
    }

    @Override
    public String getPassword() {
        return user.getPassword();
    }

    @Override
    public String getUsername() {
        return user.getUsername();
    }

    @Override
    public boolean isAccountNonExpired() {
        return true;
    }

    @Override
    public boolean isAccountNonLocked() {
        return true;
    }

    @Override
    public boolean isCredentialsNonExpired() {
        return true;
    }

    @Override
    public boolean isEnabled() {
        return user.getStatus() != null && user.getStatus() == 1;
    }

    public List<GrantedAuthority> authoritiesList() {
        return List.copyOf(getAuthorities());
    }
}
