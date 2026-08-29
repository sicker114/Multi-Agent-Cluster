package com.enterprise.agent.module.business.service;

import com.enterprise.agent.module.business.dto.SafeQueryRequest;

import java.util.List;
import java.util.Map;

/**
 * 业务数据安全查询服务。供 Python SQL Agent 通过内部接口调用，仅提供只读统计能力。
 *
 * @author enterprise-agent
 */
public interface BusinessDataService {

    /**
     * 统一安全查询入口。根据 queryType 分发到参数化统计或受控原始 SQL。
     *
     * @param request 查询请求
     * @return 查询结果列表
     */
    List<Map<String, Object>> safeQuery(SafeQueryRequest request);
}
