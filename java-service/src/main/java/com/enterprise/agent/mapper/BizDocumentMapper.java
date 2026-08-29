package com.enterprise.agent.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.enterprise.agent.entity.BizDocument;
import org.apache.ibatis.annotations.Mapper;

/**
 * 文档知识库 Mapper。
 *
 * @author enterprise-agent
 */
@Mapper
public interface BizDocumentMapper extends BaseMapper<BizDocument> {
}
