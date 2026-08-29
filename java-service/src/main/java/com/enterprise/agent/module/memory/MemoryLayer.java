package com.enterprise.agent.module.memory;

import lombok.Getter;

/**
 * 四层分层记忆枚举。
 * <ul>
 *   <li>WORKING  工作内存：单次任务临时上下文，任务结束自动销毁</li>
 *   <li>SESSION  会话缓存：单次对话短期上下文，连续提问复用</li>
 *   <li>LONG_TERM 长期业务记忆：历史问答报告、高频问题、幻觉错误案例</li>
 *   <li>SKILL    技能库：通用 SQL 模板、报告模板、检索策略（永久）</li>
 * </ul>
 *
 * @author enterprise-agent
 */
@Getter
public enum MemoryLayer {

    WORKING("mem:working"),
    SESSION("mem:session"),
    LONG_TERM("mem:longterm"),
    SKILL("mem:skill");

    /** Redis key 前缀。 */
    private final String prefix;

    MemoryLayer(String prefix) {
        this.prefix = prefix;
    }
}
