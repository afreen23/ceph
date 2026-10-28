import { HttpClientTestingModule } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { By } from '@angular/platform-browser';

import { of, throwError } from 'rxjs';

import { HardwareService } from '~/app/shared/api/hardware.service';
import { HardwareHostResponse } from '~/app/shared/enum/hardware.enum';
import { SharedModule } from '~/app/shared/shared.module';
import { configureTestBed } from '~/testing/unit-test-helper';
import { HostHardwareComponent } from './host-hardware.component';

describe('HostHardwareComponent', () => {
  let component: HostHardwareComponent;
  let fixture: ComponentFixture<HostHardwareComponent>;
  const hardwareServiceSpy = { getHost: jest.fn() };

  const sensor = (name: string, physical_context: string, reading: number) => ({
    name,
    physical_context,
    reading
  });
  const drive = (id: string, health: string) => ({ id, chassis_id: '1', health });
  const report = {
    status: {
      storage: { total: 2, components: [drive('nvme0', 'OK'), drive('nvme1', 'Warning')] },
      temperatures: {
        components: [
          sensor('CPU1 Temp', 'CPU', 44),
          sensor('CPU2 Temp', 'CPU', 47.6),
          sensor('Inlet Temp', 'Intake', 24),
          sensor('NVMe 0', 'StorageDevice', 52)
        ]
      }
    },
    firmware: { BMC: '4.86.00', BIOS: '2.14.1' },
    compression: { fcm_drive_count: 2, savings_bytes: 17.1 * 1024 ** 4, compression_ratio: 4.21 }
  } as unknown as HardwareHostResponse;

  configureTestBed({
    declarations: [HostHardwareComponent],
    imports: [HttpClientTestingModule, SharedModule],
    providers: [{ provide: HardwareService, useValue: hardwareServiceSpy }]
  });

  const load = (hardware: object) => {
    hardwareServiceSpy.getHost.mockReturnValue(hardware);
    fixture = TestBed.createComponent(HostHardwareComponent);
    component = fixture.componentInstance;
    fixture.componentRef.setInput('hostname', 'node-1');
    fixture.detectChanges();
  };
  const field = (label: string) => component.fields().find((f) => f.label === label);
  const text = () => fixture.nativeElement.textContent;

  beforeEach(() => {
    hardwareServiceSpy.getHost.mockReset();
  });

  it('should show the hardware of the host', () => {
    load(of(report));

    expect(hardwareServiceSpy.getHost).toHaveBeenCalledWith('node-1');
    expect(component.fields().map((f) => [f.label, f.value])).toEqual([
      ['CPU temperature', '48°C'],
      ['Drive temperature', '52°C'],
      ['Drives', 2],
      ['BMC', '4.86.00'],
      ['BIOS', '2.14.1'],
      ['Savings', '17.1 TiB'],
      ['Compression ratio', '4.21:1']
    ]);
    expect(text()).toContain('Hardware');
  });

  it('should leave out savings when the host has no FCM drives', () => {
    load(of({ ...report, compression: null }));

    expect(field('BMC')?.value).toBe('4.86.00');
    expect(field('Savings')).toBeUndefined();
  });

  it('should show a message and no error without a node-proxy report', () => {
    const error = { status: 404, preventDefault: jest.fn() };
    load(throwError(error));

    expect(error.preventDefault).toHaveBeenCalled();
    expect(component.hardware()).toBeNull();
    expect(text()).toContain('No hardware data is reported for this host.');
  });

  it('should report errors other than a missing node-proxy report', () => {
    const error = { status: 500, preventDefault: jest.fn() };
    load(throwError(error));

    expect(error.preventDefault).not.toHaveBeenCalled();
  });

  it('should list the hardware drives', () => {
    load(of(report));

    expect(text()).toContain("Drives as reported by the server's BMC: 2 drives.");
    expect(fixture.debugElement.query(By.css('cd-table'))).toBeTruthy();
    expect(component.drives().map((d) => d.uid)).toEqual(['1/nvme0', '1/nvme1']);
  });

  it('should hide the hardware drives when the host reports none', () => {
    load(of({ ...report, status: { ...report.status, storage: { total: 0, components: [] } } }));

    expect(text()).not.toContain('Hardware drives');
  });
});
