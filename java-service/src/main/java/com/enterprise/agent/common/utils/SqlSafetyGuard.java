package com.enterprise.agent.common.utils;

import cn.hutool.core.util.StrUtil;
import com.enterprise.agent.common.exception.BusinessException;
import com.enterprise.agent.common.response.ResultCode;

import java.util.regex.Pattern;

/**
 * 高危 SQL 拦截守卫。
 * <p>SQL Agent 生成的查询语句在 Java 侧执行前必须经过本守卫校验：
 * 仅允许单条 SELECT 只读语句，拦截 DELETE/UPDATE/INSERT/ALTER/DROP/TRUNCATE 等写操作，
 * 拦截多语句、注释注入、危险函数。</p>
 *
 * @author enterprise-agent
 */
public final class SqlSafetyGuard {

    private SqlSafetyGuard() {
    }

    /** 高危关键字（写操作 / DDL / 危险函数）。 */
    private static final Pattern DANGEROUS_KEYWORDS = Pattern.compile(
            "\\b(insert|update|delete|drop|alter|truncate|create|rename|replace|grant|revoke|" +
                    "merge|call|exec|execute|load_file|outfile|dumpfile|into\\s+outfile|" +
                    "information_schema|sleep|benchmark|shutdown)\\b",
            Pattern.CASE_INSENSITIVE);

    /** 多语句 / 注释注入。 */
    private static final Pattern INJECTION = Pattern.compile("(;\\s*\\S)|(--)|(/\\*)|(#)");

    /**
     * 校验 SQL 是否为安全只读语句。不安全直接抛出 {@link BusinessException}。
     *
     * @param sql 待执行 SQL
     */
    public static void check(String sql) {
        if (StrUtil.isBlank(sql)) {
            throw new BusinessException(ResultCode.SQL_ONLY_READONLY, "SQL 不能为空");
        }
        String normalized = sql.trim();

        // 1. 必须以 SELECT / WITH 开头（只读）
        String lower = normalized.toLowerCase();
        if (!(lower.startsWith("select") || lower.startsWith("with"))) {
            throw new BusinessException(ResultCode.SQL_ONLY_READONLY);
        }

        // 2. 拦截多语句、注释注入
        // 去掉末尾单个分号后再判定，允许 "select ...;" 形式
        String noTailSemicolon = normalized.endsWith(";")
                ? normalized.substring(0, normalized.length() - 1) : normalized;
        if (INJECTION.matcher(noTailSemicolon).find()) {
            throw new BusinessException(ResultCode.SQL_DANGEROUS, "检测到多语句或注释注入");
        }

        // 3. 拦截高危关键字
        if (DANGEROUS_KEYWORDS.matcher(noTailSemicolon).find()) {
            throw new BusinessException(ResultCode.SQL_DANGEROUS);
        }
    }

    /** 返回布尔结果的软校验，不抛异常。 */
    public static boolean isSafe(String sql) {
        try {
            check(sql);
            return true;
        } catch (BusinessException e) {
            return false;
        }
    }
}
