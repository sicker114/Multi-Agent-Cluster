package com.enterprise.agent.common.utils;

import cn.hutool.core.util.StrUtil;

import java.util.regex.Pattern;

/**
 * 敏感信息脱敏工具类。
 * <p>用于文档内容拉取、报告返回、日志打印场景下自动隐藏手机号、身份证、银行卡、
 * 财务机密数字（金额 &gt; 6 位）、邮箱等敏感字段。</p>
 *
 * @author enterprise-agent
 */
public final class DesensitizeUtil {

    private DesensitizeUtil() {
    }

    /** 手机号：保留前 3 后 4。 */
    private static final Pattern PHONE = Pattern.compile("(?<!\\d)(1[3-9]\\d)\\d{4}(\\d{4})(?!\\d)");
    /** 身份证 18 位：保留前 4 后 4。 */
    private static final Pattern ID_CARD = Pattern.compile("(?<!\\d)(\\d{4})\\d{10}([0-9Xx]{4})(?!\\d)");
    /** 银行卡 16-19 位：保留后 4。 */
    private static final Pattern BANK_CARD = Pattern.compile("(?<!\\d)\\d{12,15}(\\d{4})(?!\\d)");
    /** 邮箱：隐藏用户名中间部分。 */
    private static final Pattern EMAIL = Pattern.compile("(\\w{1,3})[^@]*(@\\w+\\.\\w+)");
    /** 大额财务数字（连续 7 位及以上数字，视为机密金额）。 */
    private static final Pattern BIG_MONEY = Pattern.compile("(?<!\\d)(\\d{2})\\d{5,}(\\d{2})(?!\\d)");

    /**
     * 对整段文本执行综合脱敏。文档拉取给 Python 前必须调用，防止敏感信息外泄。
     *
     * @param text 原始文本
     * @return 脱敏后的文本
     */
    public static String desensitizeText(String text) {
        if (StrUtil.isBlank(text)) {
            return text;
        }
        String result = text;
        result = PHONE.matcher(result).replaceAll("$1****$2");
        result = ID_CARD.matcher(result).replaceAll("$1**********$2");
        result = BANK_CARD.matcher(result).replaceAll("**** **** **** $1");
        result = EMAIL.matcher(result).replaceAll("$1***$2");
        result = BIG_MONEY.matcher(result).replaceAll("$1*****$2");
        return result;
    }

    /** 手机号单独脱敏。 */
    public static String desensitizePhone(String phone) {
        if (StrUtil.isBlank(phone) || phone.length() != 11) {
            return phone;
        }
        return StrUtil.hide(phone, 3, 7);
    }

    /** 身份证单独脱敏。 */
    public static String desensitizeIdCard(String idCard) {
        if (StrUtil.isBlank(idCard) || idCard.length() < 8) {
            return idCard;
        }
        return StrUtil.hide(idCard, 4, idCard.length() - 4);
    }
}
