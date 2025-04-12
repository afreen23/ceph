import { Component, OnDestroy, OnInit } from '@angular/core';

import { NgbActiveModal } from '@ng-bootstrap/ng-bootstrap';
import { detect } from 'detect-browser';
import { Subscription } from 'rxjs';

import { UserService } from '~/app/shared/api/user.service';
import { AppConstants, USER, VERSION_PREFIX } from '~/app/shared/constants/app.constants';
import { LocalStorage } from '~/app/shared/enum/local-storage-enum';
import { Permission } from '~/app/shared/models/permissions';
import { AuthStorageService } from '~/app/shared/services/auth-storage.service';
import { SummaryService } from '~/app/shared/services/summary.service';

@Component({
  selector: 'cd-about',
  templateUrl: './about.component.html',
  styleUrls: ['./about.component.scss']
})
export class AboutComponent implements OnInit, OnDestroy {
  modalVariables: any;
  subs: Subscription;
  userPermission: Permission;
  projectConstants: typeof AppConstants;
  hostAddr: string;
  copyright: string;
  version: string;

  constructor(
    public activeModal: NgbActiveModal,
    private summaryService: SummaryService,
    private userService: UserService,
    private authStorageService: AuthStorageService
  ) {
    this.userPermission = this.authStorageService.getPermissions().user;
  }

  ngOnInit() {
    this.projectConstants = AppConstants;
    this.hostAddr = window.location.hostname;
    this.modalVariables = this.setVariables();
    this.subs = this.summaryService.subscribe((summary) => {
      this.version = summary.version.startsWith(VERSION_PREFIX)
        ? summary.version.replace(VERSION_PREFIX, '').split(' ')[0]
        : summary.version;
      this.hostAddr = summary.mgr_host.replace(/(^\w+:|^)\/\//, '').replace(/\/$/, '');
    });
  }

  ngOnDestroy(): void {
    this.subs.unsubscribe();
  }

  setVariables() {
    const project = {} as any;
    project.user = localStorage.getItem(LocalStorage.DASHBOARD_USRENAME);
    project.role = USER;
    if (this.userPermission.read) {
      this.userService.get(project.user).subscribe((data: any) => {
        project.role = data.roles;
      });
    }
    const browser = detect();
    project.browserName = browser && browser.name ? browser.name : $localize`Not detected`;
    project.browserVersion = browser && browser.version ? browser.version : $localize`Not detected`;
    project.browserOS = browser && browser.os ? browser.os : $localize`Not detected`;
    return project;
  }
}
