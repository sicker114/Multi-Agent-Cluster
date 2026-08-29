package com.enterprise.agent.module.file.controller;

import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.enterprise.agent.common.response.R;
import com.enterprise.agent.entity.BizDocument;
import com.enterprise.agent.module.file.service.DocumentService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.RequiredArgsConstructor;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;

/**
 * 知识库文件管理控制器：上传、分页、删除。
 *
 * @author enterprise-agent
 */
@Tag(name = "知识库文档管理", description = "PDF/Word/TXT 上传与管理")
@RestController
@RequestMapping("/api/file")
@RequiredArgsConstructor
public class DocumentController {

    private final DocumentService documentService;

    @Operation(summary = "上传知识库文档", description = "支持 pdf/doc/docx/txt，元数据落库并归属当前用户部门")
    @PreAuthorize("hasAuthority('file:upload')")
    @PostMapping("/upload")
    public R<BizDocument> upload(@Parameter(description = "文件") @RequestParam("file") MultipartFile file,
                                 @Parameter(description = "文档分类") @RequestParam(value = "category", required = false) String category) {
        return R.success("上传成功", documentService.upload(file, category));
    }

    @Operation(summary = "分页查询知识库文档")
    @PreAuthorize("hasAuthority('file:upload')")
    @GetMapping("/page")
    public R<Page<BizDocument>> page(@RequestParam(defaultValue = "1") long pageNo,
                                     @RequestParam(defaultValue = "10") long pageSize,
                                     @RequestParam(required = false) String keyword) {
        return R.success(documentService.pageList(pageNo, pageSize, keyword));
    }

    @Operation(summary = "删除知识库文档")
    @PreAuthorize("hasAuthority('file:manage')")
    @DeleteMapping("/{docId}")
    public R<Void> delete(@PathVariable Long docId) {
        documentService.delete(docId);
        return R.success();
    }
}
