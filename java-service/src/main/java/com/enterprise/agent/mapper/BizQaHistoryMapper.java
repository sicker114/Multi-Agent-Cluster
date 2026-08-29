package com.enterprise.agent.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.enterprise.agent.entity.BizQaHistory;
import org.apache.ibatis.annotations.Mapper;

/**
 * 问答历史 Mapper。
 *
 * @author enterprise-agent
 */
@Mapper
public interface BizQaHistoryMapper extends BaseMapper<BizQaHistory> {
}
