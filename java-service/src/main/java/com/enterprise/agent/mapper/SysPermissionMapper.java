package com.enterprise.agent.mapper;

import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Select;

import java.util.List;

/**
 * 权限 Mapper：按用户查权限标识集合。
 *
 * @author enterprise-agent
 */
@Mapper
public interface SysPermissionMapper {

    /**
     * 查询用户拥有的全部权限标识（perm_code）。
     *
     * @param userId 用户ID
     * @return 权限标识列表
     */
    @Select("""
            SELECT DISTINCT p.perm_code FROM sys_permission p
            INNER JOIN sys_role_permission rp ON rp.perm_id = p.id
            INNER JOIN sys_user_role ur ON ur.role_id = rp.role_id
            WHERE ur.user_id = #{userId}
            """)
    List<String> selectPermCodesByUserId(Long userId);
}
