;;; init.el --- privatestack dev_ide brick -*- lexical-binding: t -*-
;; Emacs as the IDE: eglot + one language server per stack, Mocha end
;; to end. First launch installs the packages below from (M)ELPA - give
;; it a minute, once.

;;; packages
(require 'package)
(add-to-list 'package-archives '("melpa" . "https://melpa.org/packages/") t)
(package-initialize)
(setq use-package-always-ensure t)

;;; sane defaults
(setq make-backup-files nil
      auto-save-default nil
      create-lockfiles nil
      ring-bell-function 'ignore
      use-short-answers t)
(recentf-mode 1)
(savehist-mode 1)
(electric-pair-mode 1)
(column-number-mode 1)
(add-hook 'prog-mode-hook #'display-line-numbers-mode)
(which-key-mode 1)

;;; the look: Catppuccin Mocha + a modeline that earns its pixels
(use-package catppuccin-theme
  :config
  (setq catppuccin-flavor 'mocha)
  (load-theme 'catppuccin :no-confirm))
(use-package nerd-icons)
(use-package doom-modeline
  :init (doom-modeline-mode 1))
(set-face-attribute 'default nil
                    :family "JetBrainsMono Nerd Font" :height 110)

;;; navigation: vertico stack + consult
(use-package vertico
  :init (vertico-mode 1))
(use-package orderless
  :custom
  (completion-styles '(orderless basic))
  (completion-category-overrides '((file (styles basic partial-completion)))))
(use-package marginalia
  :init (marginalia-mode 1))
(use-package consult
  :bind (("C-s"   . consult-line)
         ("C-x b" . consult-buffer)
         ("M-y"   . consult-yank-pop)
         ("C-c g" . consult-ripgrep)))

;;; completion in buffer
(use-package corfu
  :custom
  (corfu-auto t)
  (corfu-cycle t)
  :init (global-corfu-mode 1))

;;; LSP: eglot (built in) - servers arrive from the brick, not from here
(use-package yaml-mode)
(with-eval-after-load 'eglot
  ;; every yaml in this stack is ansible: hand it to ansible-language-server
  (add-to-list 'eglot-server-programs
               '((yaml-mode yaml-ts-mode)
                 . ("ansible-language-server" "--stdio"))))
(dolist (hook '(java-mode-hook java-ts-mode-hook
                js-mode-hook js-ts-mode-hook typescript-ts-mode-hook
                mhtml-mode-hook html-mode-hook css-mode-hook css-ts-mode-hook
                sh-mode-hook bash-ts-mode-hook
                yaml-mode-hook yaml-ts-mode-hook))
  (add-hook hook #'eglot-ensure))
(setq eglot-autoshutdown t)

;;; diagnostics on the keyboard
(with-eval-after-load 'flymake
  (define-key flymake-mode-map (kbd "M-n") #'flymake-goto-next-error)
  (define-key flymake-mode-map (kbd "M-p") #'flymake-goto-prev-error))

;;; git
(use-package magit
  :bind ("C-x g" . magit-status))

;;; project terminal (eat: pure elisp, no native deps)
(use-package eat)
(defun privatestack/project-terminal ()
  "Open a terminal in the current project root."
  (interactive)
  (let ((default-directory
         (or (when-let ((p (project-current))) (project-root p))
             default-directory)))
    (eat)))
(global-set-key (kbd "C-c t") #'privatestack/project-terminal)
