package com.enterprise.agent.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.enterprise.agent.entity.SysRole;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Select;

import java.util.List;

/**
 * 角色 Mapper，含按用户查角色。
 *
 * @author enterprise-agent
 */
@Mapper
public interface SysRoleMapper extends BaseMapper<SysRole> {

    /**
     * 查询用户拥有的全部角色。
     *
     * @param userId 用户ID
     * @return 角色列表
     */
    @Select("""
            SELECT r.* FROM sys_role r
            INNER JOIN sys_user_role ur ON ur.role_id = r.id
            WHERE ur.user_id = #{userId} AND r.deleted = 0
            """)
    List<SysRole> selectRolesByUserId(Long userId);
}
