package com.enterprise.agent.security;

import com.enterprise.agent.common.exception.BusinessException;
import com.enterprise.agent.common.response.ResultCode;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;

import java.util.Collections;
import java.util.List;

/**
 * 安全上下文工具类：获取当前登录用户，计算数据权限部门范围。
 *
 * @author enterprise-agent
 */
public final class SecurityUtil {

    private SecurityUtil() {
    }

    /** 获取当前登录用户，未登录抛出未授权异常。 */
    public static LoginUser currentUser() {
        Authentication auth = SecurityContextHolder.getContext().getAuthentication();
        if (auth == null || !(auth.getPrincipal() instanceof LoginUser loginUser)) {
            throw new BusinessException(ResultCode.UNAUTHORIZED);
        }
        return loginUser;
    }

    public static Long currentUserId() {
        return currentUser().getUserId();
    }

    public static Long currentDeptId() {
        return currentUser().getDeptId();
    }

    /**
     * 计算当前用户可访问的数据部门范围。
     * <p>数据范围 1（全部）返回 null，表示不限制；数据范围 2（本部门）返回本部门ID列表。</p>
     *
     * @return null 表示全量，否则为受限部门列表
     */
    public static List<Long> dataScopeDeptIds() {
        LoginUser user = currentUser();
        if (user.getDataScope() != null && user.getDataScope() == 1) {
            return null; // 全量数据权限
        }
        return Collections.singletonList(user.getDeptId());
    }

    /**
     * 越权校验：普通用户访问非本部门数据时拦截。
     *
     * @param targetDeptId 目标数据所属部门
     */
    public static void checkDataScope(Long targetDeptId) {
        List<Long> scope = dataScopeDeptIds();
        if (scope != null && !scope.contains(targetDeptId)) {
            throw new BusinessException(ResultCode.DATA_SCOPE_DENIED);
        }
    }
}
