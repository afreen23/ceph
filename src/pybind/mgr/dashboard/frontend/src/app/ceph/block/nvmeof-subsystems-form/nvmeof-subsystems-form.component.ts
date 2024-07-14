import { Component, OnInit } from '@angular/core';
import { UntypedFormArray, UntypedFormControl, Validators } from '@angular/forms';
import { NgbActiveModal } from '@ng-bootstrap/ng-bootstrap';

import { CdFormBuilder } from '~/app/shared/forms/cd-form-builder';
import { ActionLabelsI18n, URLVerbs } from '~/app/shared/constants/app.constants';
import { CdFormGroup } from '~/app/shared/forms/cd-form-group';
import { CdValidators } from '~/app/shared/forms/cd-validators';
import { Permission } from '~/app/shared/models/permissions';
import { AuthStorageService } from '~/app/shared/services/auth-storage.service';
import { TaskWrapperService } from '~/app/shared/services/task-wrapper.service';
import { FinishedTask } from '~/app/shared/models/finished-task';
import { ActivatedRoute, Router } from '@angular/router';
import { NvmeofService } from '~/app/shared/api/nvmeof.service';
import { NvmeofSubsystemHost } from '~/app/shared/models/nvmeof';

@Component({
  selector: 'cd-nvmeof-subsystems-form',
  templateUrl: './nvmeof-subsystems-form.component.html',
  styleUrls: ['./nvmeof-subsystems-form.component.scss']
})
export class NvmeofSubsystemsFormComponent implements OnInit {
  permission: Permission;
  subsystemForm: CdFormGroup;
  action: string;
  resource: string;
  pageURL: string;
  edit: boolean = false;

  DEFAULT_NQN = 'nqn.2001-07.com.ceph:' + Date.now();

  constructor(
    private authStorageService: AuthStorageService,
    public actionLabels: ActionLabelsI18n,
    public activeModal: NgbActiveModal,
    private nvmeofService: NvmeofService,
    private taskWrapperService: TaskWrapperService,
    private router: Router,
    private route: ActivatedRoute,
    private formBuilder: CdFormBuilder
  ) {
    this.permission = this.authStorageService.getPermissions().nvmeof;
    this.resource = $localize`Subsystem`;
    this.pageURL = 'block/nvmeof/subsystems';
  }

  NQN_REGEX = /^nqn\.(19|20)\d\d-(0[1-9]|1[0-2])\.\D{2,3}(\.[A-Za-z0-9-]+)+(:[A-Za-z0-9-\.]+)$/;
  NQN_REGEX_UUID = /^nqn\.2014-08\.org\.nvmexpress:uuid:[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/;

  customNQNValidator = CdValidators.custom(
    'pattern',
    (nqnInput: string) =>
      !!nqnInput && !(this.NQN_REGEX.test(nqnInput) || this.NQN_REGEX_UUID.test(nqnInput))
  );

  ngOnInit() {
    this.createForm();
    this.action = this.actionLabels.CREATE;
    if (this.router.url.includes('subsystems/(modal:edit')) {
      this.edit = true;
      this.action = this.actionLabels.EDIT;
      this.route.params.subscribe((params: { subsystem_nqn: string; max_ns: any }) => {
        this.subsystemForm.get('nqn').setValue(params.subsystem_nqn);
        this.subsystemForm.get('max_namespaces').setValue(params.max_ns);
        this.subsystemForm.get('nqn').disable();
        this.subsystemForm.get('max_namespaces').disable();
        this.nvmeofService
          .getInitiators(params.subsystem_nqn)
          .subscribe((initiators: NvmeofSubsystemHost[]) => {
            if (initiators[0].nqn !== '*') {
              this.subsystemForm.get('initiators').setValue('add-host');
              initiators.forEach((init: NvmeofSubsystemHost) => this.addHost(init.nqn));
            }
          });
      });
    }
  }

  createForm() {
    this.subsystemForm = new CdFormGroup({
      nqn: new UntypedFormControl(this.DEFAULT_NQN, {
        validators: [
          Validators.required,
          this.customNQNValidator,
          CdValidators.custom(
            'maxLength',
            (nqnInput: string) => new TextEncoder().encode(nqnInput).length > 223
          )
        ],
        asyncValidators: [
          CdValidators.unique(this.nvmeofService.isSubsystemPresent, this.nvmeofService)
        ]
      }),
      max_namespaces: new UntypedFormControl(256, {
        validators: [CdValidators.number(false), Validators.max(256), Validators.min(1)]
      }),
      initiators: new UntypedFormControl('all'),
      hosts: this.formBuilder.array(
        [],
        CdValidators.custom(
          'duplicate',
          (hosts: string[]) => !!hosts.length && new Set(hosts)?.size !== hosts.length
        )
      )
    });
  }

  get hosts(): UntypedFormArray {
    return this.subsystemForm.get('hosts') as UntypedFormArray;
  }

  addHost(hostNQN?: string) {
    const newHostFormGroup = this.formBuilder.control(hostNQN ? hostNQN : '', [
      this.customNQNValidator,
      Validators.required
    ]);
    this.hosts.push(newHostFormGroup);
  }

  removeHost(index: number) {
    this.hosts.removeAt(index);
  }

  onInitiatorSelect(selected: string) {
    switch (selected) {
      case 'all':
        while (this.hosts.length !== 0) this.hosts.removeAt(0);
        break;
      case 'add-host':
        if (this.hosts.length === 0) {
          this.addHost();
        }
        break;
    }
  }

  onSubmit() {
    const component = this;
    const nqn: string = this.subsystemForm.getValue('nqn');
    const max_namespaces: number = Number(this.subsystemForm.getValue('max_namespaces'));
    const initiators: string = this.subsystemForm.getValue('initiators');
    const hosts: string[] = this.hosts.value;
    let taskUrl = `nvmeof/subsystem/${URLVerbs.CREATE}`;
    let hostNQN: string = '';

    if (hosts.length === 0 && initiators === 'all') {
      hostNQN = '*';
    } else {
      hostNQN = hosts.join(',');
    }

    if (this.edit) {
      taskUrl = `nvmeof/subsystem/${URLVerbs.EDIT}`;
      this.taskWrapperService
        .wrapTaskAroundCall({
          task: new FinishedTask(taskUrl, {
            nqn: nqn
          }),
          call: this.nvmeofService.updateInitiators(nqn, hostNQN)
        })
        .subscribe({
          error() {
            component.subsystemForm.setErrors({ cdSubmitButton: true });
          },
          complete: () => {
            this.router.navigate([this.pageURL, { outlets: { modal: null } }]);
          }
        });
    } else {
      const request = {
        nqn,
        max_namespaces,
        enable_ha: true,
        initiators: hostNQN
      };

      if (!max_namespaces) {
        delete request.max_namespaces;
      }
      this.taskWrapperService
        .wrapTaskAroundCall({
          task: new FinishedTask(taskUrl, {
            nqn: nqn
          }),
          call: this.nvmeofService.createSubsystem(request)
        })
        .subscribe({
          error() {
            component.subsystemForm.setErrors({ cdSubmitButton: true });
          },
          complete: () => {
            this.router.navigate([this.pageURL, { outlets: { modal: null } }]);
          }
        });
    }
  }
}
