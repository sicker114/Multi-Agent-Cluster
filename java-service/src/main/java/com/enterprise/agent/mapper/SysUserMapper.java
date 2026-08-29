package com.enterprise.agent.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.enterprise.agent.entity.SysUser;
import org.apache.ibatis.annotations.Mapper;

/**
 * 用户 Mapper。
 *
 * @author enterprise-agent
 */
@Mapper
public interface SysUserMapper extends BaseMapper<SysUser> {
}
