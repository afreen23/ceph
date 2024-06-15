import { TestBed } from '@angular/core/testing';
<<<<<<< HEAD
import { HttpClientTestingModule, HttpTestingController } from '@angular/common/http/testing';
import { configureTestBed } from '~/testing/unit-test-helper';
import { NvmeofService } from './nvmeof.service';

describe('NvmeofService', () => {
  let service: NvmeofService;
  let httpTesting: HttpTestingController;

  configureTestBed({
    providers: [NvmeofService],
    imports: [HttpClientTestingModule]
  });

  beforeEach(() => {
    service = TestBed.inject(NvmeofService);
    httpTesting = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpTesting.verify();
=======

import { NvmeofService } from './nvmeof.service';

describe('NvmeofTcpService', () => {
  let service: NvmeofService;

  beforeEach(() => {
    TestBed.configureTestingModule({});
    service = TestBed.inject(NvmeofService);
>>>>>>> 151d9595398 (mgr/dashboard: Introduce subsytems)
  });

  it('should be created', () => {
    expect(service).toBeTruthy();
  });
<<<<<<< HEAD

  it('should call listGateways', () => {
    service.listGateways().subscribe();
    const req = httpTesting.expectOne('api/nvmeof/gateway');
    expect(req.request.method).toBe('GET');
  });
=======
>>>>>>> 151d9595398 (mgr/dashboard: Introduce subsytems)
});
